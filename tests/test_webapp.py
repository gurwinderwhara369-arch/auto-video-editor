from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web.webapp.jobs import JobConfig, create_job, load_status, run_job, safe_media_path
from app.web.webapp.server import app
from app.cli.render_reel import load_or_analyze_moments, metadata_matches_clips_dir, moments_match_metadata
from app.engine.core.models import ClipMetadata, ClipMetadataSet, CropMetadata, MomentMetadata, MomentMetadataSet


def test_home_page_loads() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Start New Reel" in response.text
    assert "Available Template" in response.text
    assert "Scan New Trend" in response.text
    assert "Advanced" in response.text
    assert "Pro Layer" in response.text
    assert "Production Jobs" in response.text


def test_safe_media_path_rejects_outside_workspace() -> None:
    with pytest.raises(ValueError):
        safe_media_path("/etc/passwd")


def test_dry_run_job_creates_status_and_artifacts(tmp_path: Path) -> None:
    trend = tmp_path / "trend.mp4"
    clips = tmp_path / "clips"
    clips.mkdir()
    trend.write_bytes(b"fake")
    (clips / "clip.mp4").write_bytes(b"fake")
    config = JobConfig(
        trend_video=trend,
        clips_dir=clips,
        output_name="final.mp4",
        render_mode="pro_layer",
        dry_run=True,
    )

    job_id = create_job(config, job_id="test_dry_run_job", autostart=False)
    run_job(job_id, config)
    status = load_status(job_id)

    assert status["status"] == "completed"
    assert status["phase"] == "review"
    assert status["config"]["render_mode"] == "pro_layer"
    assert status["metrics"]["variants"] == 0
    assert status["artifacts"]["qa_report"].endswith("qa_report.json")


def test_scan_confirmation_page_loads(tmp_path: Path) -> None:
    job_id = "test_scan_done"
    job_dir = Path("workspace/web_jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job_status.json").write_text(
        """{
  "job_id": "test_scan_done",
  "status": "completed",
  "step": "Template ready",
  "phase": "footage",
  "job_type": "template_scan",
  "created_at": "2026-05-02T00:00:00+00:00",
  "updated_at": "2026-05-02T00:00:00+00:00",
  "config": {"trend_video": "assets/reference_trends/Montagem Tentana Trend 1.mp4"},
  "summary": {"duration": 15, "segments": 12, "beats": 24, "flashes": 2},
  "artifacts": {"template": "workspace/web_jobs/test_scan_done/template.json"},
  "events": [{"time": "2026-05-02T00:00:00+00:00", "message": "Template scan complete"}]
}
""",
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.get(f"/template-scans/{job_id}")

    assert response.status_code == 200
    assert "Use This Template & Continue" in response.text
    assert "Scan summary" in response.text


def test_job_page_shows_command_center_panels() -> None:
    client = TestClient(app)

    response = client.get("/jobs/test_dry_run_job")

    assert response.status_code == 200
    assert "Live processing" in response.text
    assert "Processing Metrics" in response.text
    assert "Live Log" in response.text


def test_failed_job_page_shows_developer_details(tmp_path: Path) -> None:
    job_id = "test_failed_job"
    job_dir = Path("workspace/web_jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job_status.json").write_text(
        """{
  "job_id": "test_failed_job",
  "status": "failed",
  "step": "Failed",
  "phase": "render",
  "created_at": "2026-05-02T00:00:00+00:00",
  "updated_at": "2026-05-02T00:00:00+00:00",
  "config": {},
  "error": "Command failed: ffmpeg Error opening input file missing.mp4",
  "events": [{"time": "2026-05-02T00:00:00+00:00", "message": "Command failed"}]
}
""",
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert "Needs attention" in response.text
    assert "Developer details" in response.text
    assert "Error opening input file" in response.text


def test_results_page_shows_winner_and_variant_comparison() -> None:
    client = TestClient(app)

    response = client.get("/jobs/20260502_071855_8a2a3c77/results")

    if response.status_code == 404:
        pytest.skip("Completed sample web job is not available in this workspace")
    assert response.status_code == 200
    assert "Selected output" in response.text
    assert "Variant Comparison" in response.text
    assert "Developer Artifacts" in response.text


def test_stale_metadata_is_rejected_for_selected_clips(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    stale_dir = tmp_path / "old_clips"
    clips_dir.mkdir()
    stale_dir.mkdir()
    stale_clip = stale_dir / "clip.mp4"
    stale_clip.write_bytes(b"fake")
    metadata = ClipMetadataSet(
        clips=[
            ClipMetadata(
                clip_id="clip_001",
                filename="clip.mp4",
                path=stale_clip,
                duration=1.0,
                width=540,
                height=960,
                fps=30,
                overall_score=0.5,
                sharpness_score=0.5,
                brightness_score=0.5,
                motion_score=0.5,
            )
        ]
    )

    assert metadata_matches_clips_dir(metadata, clips_dir) is False


def test_stale_moments_are_rejected_for_selected_clips(tmp_path: Path) -> None:
    clips_dir = tmp_path / "clips"
    stale_dir = tmp_path / "old_clips"
    clips_dir.mkdir()
    stale_dir.mkdir()
    current_clip = clips_dir / "clip.mp4"
    stale_clip = stale_dir / "clip.mp4"
    current_clip.write_bytes(b"fake")
    stale_clip.write_bytes(b"fake")
    metadata = ClipMetadataSet(
        clips=[
            ClipMetadata(
                clip_id="clip_001",
                filename="clip.mp4",
                path=current_clip,
                duration=1.0,
                width=540,
                height=960,
                fps=30,
                overall_score=0.5,
                sharpness_score=0.5,
                brightness_score=0.5,
                motion_score=0.5,
            )
        ]
    )
    stale_moments = MomentMetadataSet(
        moments=[
            MomentMetadata(
                moment_id="moment_001",
                clip_id="clip_001",
                source_file=stale_clip,
                start=0.0,
                end=0.5,
                duration=0.5,
                score=0.8,
                sharpness_score=0.8,
                brightness_score=0.8,
                motion_score=0.3,
                stability_score=0.7,
                crop=CropMetadata(),
            )
        ]
    )

    assert moments_match_metadata(stale_moments, metadata, clips_dir) is False


def test_missing_moments_are_generated_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip_path = clips_dir / "clip.mp4"
    clip_path.write_bytes(b"fake")
    metadata = ClipMetadataSet(
        clips=[
            ClipMetadata(
                clip_id="clip_001",
                filename="clip.mp4",
                path=clip_path,
                duration=1.0,
                width=540,
                height=960,
                fps=30,
                overall_score=0.5,
                sharpness_score=0.5,
                brightness_score=0.5,
                motion_score=0.5,
            )
        ]
    )
    generated = MomentMetadataSet(
        moments=[
            MomentMetadata(
                moment_id="moment_001",
                clip_id="clip_001",
                source_file=clip_path,
                start=0.0,
                end=0.5,
                duration=0.5,
                score=0.9,
                sharpness_score=0.9,
                brightness_score=0.8,
                motion_score=0.3,
                stability_score=0.7,
                crop=CropMetadata(crop_x=0.45, crop_y=0.55, crop_zoom=1.05),
            )
        ]
    )

    def fake_analyze_moments(*args, **kwargs):
        return generated

    monkeypatch.setattr("app.cli.render_reel.analyze_moments", fake_analyze_moments)

    moments, path = load_or_analyze_moments(
        clip_metadata=metadata,
        clips_dir=clips_dir,
        requested_path=None,
        generated_path=tmp_path / "moment_metadata.json",
    )

    assert path.exists()
    assert moments.moments[0].moment_id == "moment_001"
