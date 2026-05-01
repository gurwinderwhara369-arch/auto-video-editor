from __future__ import annotations

import argparse
from pathlib import Path

from app.engine.analyzer.clip_ranker import analyze_clips
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

    if metadata_path and metadata_path.exists():
        clip_metadata = load_json_model(metadata_path, ClipMetadataSet)
    else:
        clip_metadata = analyze_clips(clips_dir, job_id=job_id)
        write_json_model(output_path.parent / "clip_metadata.json", clip_metadata)

    beat_map: BeatMap | None = None
    if template.beat_sync:
        if beat_map_path and beat_map_path.exists():
            beat_map = load_json_model(beat_map_path, BeatMap)
        else:
            beat_map = detect_beats(song_path)
            write_json_model(output_path.parent / "beat_map.json", beat_map)
    audio_start = select_audio_window_start(beat_map, template.total_duration)
    moments: MomentMetadataSet | None = None
    if moments_path and moments_path.exists():
        moments = load_json_model(moments_path, MomentMetadataSet)

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
