from __future__ import annotations

import argparse
from pathlib import Path

from app.cli.render_reel import (
    infer_job_id,
    metadata_matches_clips_dir,
    moments_match_metadata,
)
from app.engine.analyzer.clip_ranker import analyze_clips
from app.engine.analyzer.moment_analyzer import analyze_moments
from app.engine.beat.beat_detector import detect_beats, select_audio_window_start
from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import BeatMap, ClipMetadataSet, Effect, MomentMetadataSet, TemplateRecipe
from app.engine.planner.edit_planner import build_timeline
from app.engine.renderer.canvas_renderer import CANVAS_EFFECTS, render_canvas_timeline


def run_canvas_pipeline(
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

    clip_metadata: ClipMetadataSet | None = None
    if metadata_path and metadata_path.exists():
        loaded_metadata = load_json_model(metadata_path, ClipMetadataSet)
        if metadata_matches_clips_dir(loaded_metadata, clips_dir):
            clip_metadata = loaded_metadata
    if clip_metadata is None:
        clip_metadata = analyze_clips(clips_dir, job_id=job_id)
        write_json_model(output_path.parent / "clip_metadata.json", clip_metadata)

    if beat_map_path and beat_map_path.exists():
        beat_map = load_json_model(beat_map_path, BeatMap)
    else:
        beat_map = detect_beats(song_path)
        write_json_model(output_path.parent / "beat_map.json", beat_map)

    moments: MomentMetadataSet | None = None
    if moments_path and moments_path.exists():
        loaded_moments = load_json_model(moments_path, MomentMetadataSet)
        if moments_match_metadata(loaded_moments, clip_metadata, clips_dir):
            moments = loaded_moments
    if moments is None:
        moments = analyze_moments(clip_metadata)
        write_json_model(output_path.parent / "moment_metadata.json", moments)

    timeline = build_timeline(
        template,
        clip_metadata,
        song_path,
        output_path,
        beat_map=beat_map,
        audio_start=select_audio_window_start(beat_map, template.total_duration),
        moments=moments,
    )
    timeline = timeline.model_copy(
        update={
            "timeline": [
                segment.model_copy(
                    update={
                        "effect": segment.effect.model_copy(
                            update={
                                "metadata": {
                                    **segment.effect.metadata,
                                    "canvas_effect": CANVAS_EFFECTS[segment.segment_index % len(CANVAS_EFFECTS)],
                                }
                            }
                        )
                    }
                )
                for segment in timeline.timeline
            ]
        }
    )
    write_json_model(output_path.parent / "canvas_timeline.json", timeline)
    render_canvas_timeline(
        timeline,
        temp_dir=temp_dir or output_path.parent / "_canvas_frames",
        debug=debug,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a layered canvas-style tattoo reel.")
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

    run_canvas_pipeline(
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
    print(f"Rendered canvas reel {args.output}")


if __name__ == "__main__":
    main()
