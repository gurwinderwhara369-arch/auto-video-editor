from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine.analyzer.clip_ranker import analyze_clips
from app.engine.analyzer.moment_analyzer import analyze_moments
from app.engine.beat.beat_detector import detect_beats
from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import ClipMetadataSet, MomentMetadataSet, TemplateRecipe
from app.engine.renderer.ffmpeg_runner import run_ffmpeg
from app.engine.scanner.template_builder import build_template_from_reference
from app.cli.render_variants import render_variants

ROOT = Path.cwd().resolve()
WEB_JOBS_DIR = ROOT / "workspace" / "web_jobs"
UPLOADS_DIR = ROOT / "workspace" / "uploads"


@dataclass
class JobConfig:
    trend_video: Path
    clips_dir: Path
    output_name: str = "final_selected_tattoo_reel.mp4"
    template_path: Path | None = None
    metadata_path: Path | None = None
    moments_path: Path | None = None
    dry_run: bool = False


def new_job_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]


def resolve_workspace_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def validate_job_config(config: JobConfig) -> None:
    if not config.trend_video.exists() or not config.trend_video.is_file():
        raise ValueError(f"Trend video not found: {config.trend_video}")
    if not config.clips_dir.exists() or not config.clips_dir.is_dir():
        raise ValueError(f"Clips folder not found: {config.clips_dir}")
    if config.template_path and (not config.template_path.exists() or not config.template_path.is_file()):
        raise ValueError(f"Template file not found: {config.template_path}")
    if config.metadata_path and (not config.metadata_path.exists() or not config.metadata_path.is_file()):
        raise ValueError(f"Metadata file not found: {config.metadata_path}")
    if config.moments_path and (not config.moments_path.exists() or not config.moments_path.is_file()):
        raise ValueError(f"Moment metadata file not found: {config.moments_path}")
    if not config.output_name.endswith(".mp4"):
        raise ValueError("Output name must end with .mp4")


def create_job(config: JobConfig, *, job_id: str | None = None, autostart: bool = True) -> str:
    validate_job_config(config)
    job_id = job_id or new_job_id()
    job_dir = WEB_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_status(
        job_dir,
        {
            "job_id": job_id,
            "status": "queued",
            "step": "Queued",
            "phase": "template",
            "created_at": _now(),
            "updated_at": _now(),
            "config": _config_to_json(config),
            "events": [{"time": _now(), "message": "Job queued"}],
        },
    )
    if autostart:
        thread = threading.Thread(target=run_job, args=(job_id, config), daemon=True)
        thread.start()
    return job_id


def run_job(job_id: str, config: JobConfig) -> None:
    job_dir = WEB_JOBS_DIR / job_id
    try:
        validate_job_config(config)
        _update_status(job_dir, status="running", step="Preparing workspace", phase="template", message="Preparing workspace")
        if config.dry_run:
            _dry_run_job(job_dir, config)
            return

        template_path = job_dir / "template.json"
        scan_report_path = job_dir / "scan_report.json"
        if config.template_path:
            _update_status(job_dir, step="Using selected template", phase="template", message="Using selected template")
            shutil.copy2(config.template_path, template_path)
            scan_report_path.write_text(
                json.dumps({"source": str(config.template_path), "mode": "existing_template"}, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            _update_status(job_dir, step="Scanning trend", phase="scan", message="Scanning trend template")
            build_template_from_reference(
                config.trend_video,
                output_template=template_path,
                report_path=scan_report_path,
            )

        reference_audio = job_dir / "reference_audio.m4a"
        _update_status(job_dir, step="Extracting audio", phase="scan", message="Extracting trend audio")
        extract_reference_audio(config.trend_video, reference_audio)

        beat_map_path = job_dir / "beat_map.json"
        _update_status(job_dir, step="Detecting beats", phase="scan", message="Detecting beats from trend audio")
        beat_map = detect_beats(reference_audio)
        write_json_model(beat_map_path, beat_map)

        metadata_path = config.metadata_path or (job_dir / "clip_metadata.json")
        if config.metadata_path is None:
            _update_status(job_dir, step="Analyzing clips", phase="footage", message="Analyzing tattoo clips")
            clip_metadata = analyze_clips(config.clips_dir, job_id=job_id)
            write_json_model(metadata_path, clip_metadata)
        else:
            clip_metadata = load_json_model(metadata_path, ClipMetadataSet)

        moments_path = config.moments_path or (job_dir / "moment_metadata.json")
        if config.moments_path is None:
            _update_status(job_dir, step="Finding best moments", phase="footage", message="Finding best tattoo moments and crops")
            moments = analyze_moments(clip_metadata, max_moments_per_clip=18)
            write_json_model(moments_path, moments)
        else:
            load_json_model(moments_path, MomentMetadataSet)

        variants_dir = job_dir / "variants"
        selected_output = job_dir / config.output_name
        _update_status(job_dir, step="Rendering variants", phase="render", message="Rendering clean, balanced, and aggressive variants")
        report = render_variants(
            template_path=template_path,
            clips_dir=config.clips_dir,
            song_path=reference_audio,
            output_dir=variants_dir,
            selected_output=selected_output,
            metadata_path=metadata_path,
            moments_path=moments_path,
            beat_map_path=beat_map_path,
        )
        _update_status(
            job_dir,
            status="completed",
            step="Completed",
            phase="review",
            message=f"Completed. Selected {report['selected_variant']} variant",
            artifacts=_artifacts(job_dir, selected_output, variants_dir),
        )
    except Exception as exc:
        _update_status(job_dir, status="failed", step="Failed", message=str(exc), error=str(exc))


def extract_reference_audio(reference_video: Path, output_audio: Path) -> Path:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(reference_video),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_audio),
        ]
    )
    return output_audio


def create_scan_job(trend_video: Path, *, job_id: str | None = None, autostart: bool = True) -> str:
    if not trend_video.exists() or not trend_video.is_file():
        raise ValueError(f"Trend video not found: {trend_video}")
    job_id = job_id or new_job_id()
    job_dir = WEB_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_status(
        job_dir,
        {
            "job_id": job_id,
            "status": "queued",
            "step": "Queued",
            "phase": "scan",
            "job_type": "template_scan",
            "created_at": _now(),
            "updated_at": _now(),
            "config": {"trend_video": str(trend_video), "dry_run": False},
            "events": [{"time": _now(), "message": "Template scan queued"}],
        },
    )
    if autostart:
        thread = threading.Thread(target=run_scan_job, args=(job_id, trend_video), daemon=True)
        thread.start()
    return job_id


def run_scan_job(job_id: str, trend_video: Path) -> None:
    job_dir = WEB_JOBS_DIR / job_id
    try:
        if not trend_video.exists() or not trend_video.is_file():
            raise ValueError(f"Trend video not found: {trend_video}")
        template_path = job_dir / "template.json"
        scan_report_path = job_dir / "scan_report.json"
        _update_status(job_dir, status="running", step="Scanning trend", phase="scan", message="Scanning trend timing and style")
        build_template_from_reference(trend_video, output_template=template_path, report_path=scan_report_path)

        reference_audio = job_dir / "reference_audio.m4a"
        _update_status(job_dir, step="Extracting audio", phase="scan", message="Extracting trend audio")
        extract_reference_audio(trend_video, reference_audio)

        beat_map_path = job_dir / "beat_map.json"
        _update_status(job_dir, step="Detecting beats", phase="scan", message="Detecting beat map")
        beat_map = detect_beats(reference_audio)
        write_json_model(beat_map_path, beat_map)

        summary = _scan_summary(template_path, scan_report_path, beat_map_path)
        _update_status(
            job_dir,
            status="completed",
            step="Template ready",
            phase="footage",
            message="Template scan complete",
            artifacts={
                "template": str(template_path),
                "scan_report": str(scan_report_path),
                "beat_map": str(beat_map_path),
                "reference_audio": str(reference_audio),
            },
            summary=summary,
        )
    except Exception as exc:
        _update_status(job_dir, status="failed", step="Failed", phase="scan", message=str(exc), error=str(exc))


def list_templates() -> list[dict[str, Any]]:
    templates_dir = ROOT / "templates"
    items: list[dict[str, Any]] = []
    if not templates_dir.exists():
        return items
    for path in sorted(templates_dir.glob("*.json")):
        try:
            template = load_json_model(path, TemplateRecipe)
            items.append(
                {
                    "name": template.name,
                    "template_id": template.template_id,
                    "path": str(path.relative_to(ROOT)),
                    "duration": round(template.total_duration, 2),
                    "segments": len(template.segments),
                    "source_type": "Available template",
                }
            )
        except Exception:
            items.append(
                {
                    "name": path.stem.replace("_", " ").title(),
                    "template_id": path.stem,
                    "path": str(path.relative_to(ROOT)),
                    "duration": None,
                    "segments": None,
                    "source_type": "Template file",
                }
            )
    return items


def load_status(job_id: str) -> dict[str, Any]:
    job_dir = WEB_JOBS_DIR / job_id
    status_path = job_dir / "job_status.json"
    if not status_path.exists():
        raise FileNotFoundError(job_id)
    return enrich_status(json.loads(status_path.read_text(encoding="utf-8")), job_dir)


def list_jobs() -> list[dict[str, Any]]:
    if not WEB_JOBS_DIR.exists():
        return []
    statuses = []
    for status_path in sorted(WEB_JOBS_DIR.glob("*/job_status.json"), reverse=True):
        try:
            statuses.append(enrich_status(json.loads(status_path.read_text(encoding="utf-8")), status_path.parent))
        except json.JSONDecodeError:
            continue
    return statuses


def enrich_status(status: dict[str, Any], job_dir: Path | None = None) -> dict[str, Any]:
    job_dir = job_dir or WEB_JOBS_DIR / status.get("job_id", "")
    enriched = dict(status)
    enriched["phase_progress"] = _phase_progress(enriched.get("phase", "template"), enriched.get("status", "queued"))
    enriched["current_stage_label"] = _stage_label(enriched)
    enriched["metrics"] = _job_metrics(enriched, job_dir)
    enriched["short_error"] = _short_error(enriched.get("error"))
    return enriched


def safe_media_path(path: str) -> Path:
    candidate = resolve_workspace_path(path)
    if candidate is None:
        raise ValueError("Missing media path")
    allowed_roots = [
        WEB_JOBS_DIR.resolve(),
        UPLOADS_DIR.resolve(),
        (ROOT / "workspace" / "outputs").resolve(),
        (ROOT / "workspace" / "jobs").resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError("Media path is outside allowed workspace folders")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def media_href(path: Path) -> str:
    return "/media/" + str(path.resolve().relative_to(ROOT))


def _phase_progress(active_phase: str, status: str) -> list[dict[str, str]]:
    phases = [
        ("template", "Template"),
        ("footage", "Footage"),
        ("scan", "Scan"),
        ("render", "Render"),
        ("review", "Review"),
    ]
    active_index = next((index for index, (key, _) in enumerate(phases) if key == active_phase), 0)
    progress = []
    for index, (key, label) in enumerate(phases):
        state = "pending"
        if status == "completed" or index < active_index:
            state = "done"
        if index == active_index and status != "completed":
            state = "active"
        if status == "failed" and index == active_index:
            state = "failed"
        progress.append({"key": key, "label": label, "state": state})
    return progress


def _stage_label(status: dict[str, Any]) -> str:
    if status.get("status") == "failed":
        return "Needs attention"
    if status.get("status") == "completed":
        return "Ready for review"
    labels = {
        "template": "Preparing template",
        "footage": "Analyzing footage",
        "scan": "Scanning trend structure",
        "render": "Rendering variants",
        "review": "Preparing review",
    }
    return labels.get(status.get("phase"), status.get("step") or "Working")


def _job_metrics(status: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    artifacts = status.get("artifacts") or {}
    metrics: dict[str, Any] = {
        "clips": None,
        "moments": None,
        "beats": None,
        "variants": 0,
        "selected_variant": None,
        "qa_score": None,
    }
    clip_metadata = _read_json_path(artifacts.get("clip_metadata")) or _read_json_file(job_dir / "clip_metadata.json")
    if isinstance(clip_metadata, dict):
        metrics["clips"] = len(clip_metadata.get("clips", []))

    moment_metadata = _read_json_path(artifacts.get("moment_metadata")) or _read_json_file(job_dir / "moment_metadata.json")
    if isinstance(moment_metadata, dict):
        metrics["moments"] = len(moment_metadata.get("moments", []))

    beat_map = _read_json_path(artifacts.get("beat_map")) or _read_json_file(job_dir / "beat_map.json")
    if isinstance(beat_map, dict):
        metrics["beats"] = len(beat_map.get("beats", []))

    qa_report = _read_json_path(artifacts.get("qa_report")) or _read_json_file(job_dir / "variants" / "qa_report.json")
    if isinstance(qa_report, dict):
        variants = qa_report.get("variants") or []
        metrics["variants"] = len(variants)
        metrics["selected_variant"] = qa_report.get("selected_variant")
        for item in variants:
            if item.get("variant") == metrics["selected_variant"]:
                metrics["qa_score"] = item.get("qa", {}).get("score")
                break
    else:
        variants_dir = job_dir / "variants"
        if variants_dir.exists():
            metrics["variants"] = len([path for path in variants_dir.glob("*.mp4") if path.is_file()])
    return metrics


def _read_json_path(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = resolve_workspace_path(path_value)
    if not path:
        return None
    return _read_json_file(path)


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _short_error(error: str | None) -> str | None:
    if not error:
        return None
    for marker in ("Error opening input file", "No such file or directory", "Invalid argument"):
        if marker in error:
            return marker
    return error.splitlines()[0][:180]


def _dry_run_job(job_dir: Path, config: JobConfig) -> None:
    _update_status(job_dir, step="Dry run", message="Dry run created expected folders")
    (job_dir / "variants").mkdir(parents=True, exist_ok=True)
    dry_report = {
        "selected_variant": "dry_run",
        "selected_output": str(job_dir / config.output_name),
        "variants": [],
    }
    (job_dir / "variants" / "qa_report.json").write_text(json.dumps(dry_report, indent=2) + "\n", encoding="utf-8")
    _update_status(
        job_dir,
        status="completed",
        step="Completed",
        phase="review",
        message="Dry run completed",
        artifacts={"qa_report": str(job_dir / "variants" / "qa_report.json")},
    )


def _artifacts(job_dir: Path, selected_output: Path, variants_dir: Path) -> dict[str, str]:
    artifacts = {
        "final": str(selected_output),
        "qa_report": str(variants_dir / "qa_report.json"),
        "template": str(job_dir / "template.json"),
        "scan_report": str(job_dir / "scan_report.json"),
        "beat_map": str(job_dir / "beat_map.json"),
        "clip_metadata": str(job_dir / "clip_metadata.json"),
        "moment_metadata": str(job_dir / "moment_metadata.json"),
    }
    for variant in ("clean", "balanced", "aggressive"):
        variant_path = variants_dir / f"{variant}.mp4"
        if variant_path.exists():
            artifacts[variant] = str(variant_path)
    return artifacts


def _config_to_json(config: JobConfig) -> dict[str, Any]:
    return {
        "trend_video": str(config.trend_video),
        "clips_dir": str(config.clips_dir),
        "output_name": config.output_name,
        "template_path": str(config.template_path) if config.template_path else None,
        "metadata_path": str(config.metadata_path) if config.metadata_path else None,
        "moments_path": str(config.moments_path) if config.moments_path else None,
        "dry_run": config.dry_run,
    }


def _write_status(job_dir: Path, payload: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job_status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_status(
    job_dir: Path,
    *,
    status: str | None = None,
    step: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    artifacts: dict[str, str] | None = None,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    status_path = job_dir / "job_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    if status:
        payload["status"] = status
    if step:
        payload["step"] = step
    if phase:
        payload["phase"] = phase
    if artifacts is not None:
        payload["artifacts"] = artifacts
    if summary is not None:
        payload["summary"] = summary
    if error is not None:
        payload["error"] = error
    payload["updated_at"] = _now()
    events = payload.setdefault("events", [])
    if message:
        events.append({"time": _now(), "message": message})
    _write_status(job_dir, payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def copy_upload(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return target.resolve()


def _scan_summary(template_path: Path, scan_report_path: Path, beat_map_path: Path) -> dict[str, Any]:
    template = load_json_model(template_path, TemplateRecipe)
    scan_report = json.loads(scan_report_path.read_text(encoding="utf-8")) if scan_report_path.exists() else {}
    beat_map = json.loads(beat_map_path.read_text(encoding="utf-8")) if beat_map_path.exists() else {}
    events = scan_report.get("events", {}) if isinstance(scan_report.get("events"), dict) else {}
    style = scan_report.get("style", {}) if isinstance(scan_report.get("style"), dict) else {}
    return {
        "name": template.name,
        "duration": round(template.total_duration, 2),
        "segments": len(template.segments),
        "cuts": len(scan_report.get("cut_times", scan_report.get("cuts", []))),
        "beats": len(beat_map.get("beats", [])),
        "flashes": len(events.get("flash", scan_report.get("flash_events", []))) if isinstance(events, dict) else 0,
        "style": style or template.global_style.model_dump(mode="json"),
    }
