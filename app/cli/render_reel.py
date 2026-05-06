from __future__ import annotations

import argparse
from pathlib import Path

from app.engine.analyzer.clip_ranker import analyze_clips
from app.engine.analyzer.moment_analyzer import analyze_moments
from app.engine.beat.beat_detector import detect_beats, select_audio_window_start
from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import BeatMap, ClipMetadataSet, MomentMetadataSet, TemplateRecipe
from app.engine.planner.edit_planner import build_timeline
from app.engine.renderer.final_exporter import render_timeline


def infer_job_id(output: Path) -> str:
    parent = output.parent
    return parent.name if parent.name else "local_job"


def run_pipeline(
    *,
    template_path: Path,
    clips_dir: Path,
    song_path: Path,
    output_path: Path,
    metadata_path: Path | None = None,
    moments_path: Path | None = None,
    beat_map_path: Path | None = None,
    temp_dir: Path | None = None,
    debug: bool = False,
) -> None:
    template = load_json_model(template_path, TemplateRecipe)
    job_id = infer_job_id(output_path)

    clip_metadata, _ = load_or_analyze_metadata(
        clips_dir=clips_dir,
        job_id=job_id,
        requested_path=metadata_path,
        generated_path=output_path.parent / "clip_metadata.json",
    )

    beat_map: BeatMap | None = None
    if template.beat_sync:
        if beat_map_path and beat_map_path.exists():
            beat_map = load_json_model(beat_map_path, BeatMap)
        else:
            beat_map = detect_beats(song_path)
            write_json_model(output_path.parent / "beat_map.json", beat_map)
    audio_start = select_audio_window_start(beat_map, template.total_duration)
    moments, _ = load_or_analyze_moments(
        clip_metadata=clip_metadata,
        clips_dir=clips_dir,
        requested_path=moments_path,
        generated_path=output_path.parent / "moment_metadata.json",
    )

    timeline = build_timeline(
        template,
        clip_metadata,
        song_path,
        output_path,
        beat_map=beat_map,
        audio_start=audio_start,
        moments=moments,
    )
    write_json_model(output_path.parent / "timeline.json", timeline)
    render_timeline(
        timeline,
        temp_dir=temp_dir or output_path.parent / "_temp_segments",
        debug=debug,
    )


def load_or_analyze_metadata(
    *,
    clips_dir: Path,
    job_id: str,
    requested_path: Path | None,
    generated_path: Path,
) -> tuple[ClipMetadataSet, Path]:
    if requested_path and requested_path.exists():
        loaded_metadata = load_json_model(requested_path, ClipMetadataSet)
        if metadata_matches_clips_dir(loaded_metadata, clips_dir):
            return loaded_metadata, requested_path

    clip_metadata = analyze_clips(clips_dir, job_id=job_id)
    write_json_model(generated_path, clip_metadata)
    return clip_metadata, generated_path


def load_or_analyze_moments(
    *,
    clip_metadata: ClipMetadataSet,
    clips_dir: Path,
    requested_path: Path | None,
    generated_path: Path,
    max_moments_per_clip: int = 18,
) -> tuple[MomentMetadataSet, Path]:
    if requested_path and requested_path.exists():
        loaded_moments = load_json_model(requested_path, MomentMetadataSet)
        if moments_match_metadata(loaded_moments, clip_metadata, clips_dir):
            return loaded_moments, requested_path

    moments = analyze_moments(clip_metadata, max_moments_per_clip=max_moments_per_clip)
    write_json_model(generated_path, moments)
    return moments, generated_path


def metadata_matches_clips_dir(metadata: ClipMetadataSet, clips_dir: Path) -> bool:
    clips_root = clips_dir.resolve()
    if not metadata.clips:
        return False
    for clip in metadata.clips:
        clip_path = clip.path if clip.path.is_absolute() else Path.cwd() / clip.path
        try:
            resolved = clip_path.resolve()
        except OSError:
            return False
        if not resolved.exists() or not _is_within(resolved, clips_root):
            return False
    return True


def moments_match_metadata(moments: MomentMetadataSet, metadata: ClipMetadataSet, clips_dir: Path) -> bool:
    clips_root = clips_dir.resolve()
    clip_paths = {clip.clip_id: (clip.path if clip.path.is_absolute() else Path.cwd() / clip.path).resolve() for clip in metadata.clips}
    if not moments.moments:
        return False
    for moment in moments.moments:
        source = moment.source_file if moment.source_file.is_absolute() else Path.cwd() / moment.source_file
        resolved = source.resolve()
        if moment.clip_id not in clip_paths:
            return False
        if resolved != clip_paths[moment.clip_id]:
            return False
        if not resolved.exists() or not _is_within(resolved, clips_root):
            return False
    return True


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a tattoo studio reel from clips and a template.")
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--clips", required=True, type=Path)
    parser.add_argument("--song", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--moments", type=Path, default=None)
    parser.add_argument("--beat-map", type=Path, default=None)
    parser.add_argument("--temp-dir", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    run_pipeline(
        template_path=args.template,
        clips_dir=args.clips,
        song_path=args.song,
        output_path=args.output,
        metadata_path=args.metadata,
        moments_path=args.moments,
        beat_map_path=args.beat_map,
        temp_dir=args.temp_dir,
        debug=args.debug,
    )
    print(f"Rendered {args.output}")


if __name__ == "__main__":
    main()
