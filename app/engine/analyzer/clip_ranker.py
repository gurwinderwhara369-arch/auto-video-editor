from __future__ import annotations

import argparse
from pathlib import Path

from app.engine.analyzer.brightness_detector import score_brightness
from app.engine.analyzer.clip_probe import list_video_files, probe_clip
from app.engine.analyzer.motion_analyzer import score_motion
from app.engine.analyzer.sharpness_detector import score_sharpness
from app.engine.core.io import write_json_model
from app.engine.core.models import ClipMetadata, ClipMetadataSet


def analyze_clip(path: Path, clip_id: str) -> ClipMetadata:
    probe = probe_clip(path)
    sharpness = score_sharpness(path)
    brightness = score_brightness(path)
    motion = score_motion(path)
    overall = sharpness * 0.45 + brightness * 0.25 + motion * 0.30
    return ClipMetadata(
        clip_id=clip_id,
        filename=path.name,
        path=path,
        duration=float(probe["duration"]),
        width=int(probe["width"]),
        height=int(probe["height"]),
        fps=float(probe["fps"]),
        overall_score=max(0.0, min(1.0, overall)),
        sharpness_score=sharpness,
        brightness_score=brightness,
        motion_score=motion,
        is_blurry=sharpness < 0.35,
        is_too_dark=brightness < 0.25,
        detected_moments=[],
    )


def analyze_clips(clips_dir: Path, *, job_id: str = "local_job") -> ClipMetadataSet:
    files = list_video_files(clips_dir)
    if not files:
        raise ValueError(f"No video clips found in {clips_dir}")
    clips = [analyze_clip(path, f"clip_{index + 1:03d}") for index, path in enumerate(files)]
    return ClipMetadataSet(job_id=job_id, clips=clips)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze raw tattoo clips.")
    parser.add_argument("clips", type=Path)
    parser.add_argument("--output", type=Path, default=Path("clip_metadata.json"))
    parser.add_argument("--job-id", default="local_job")
    args = parser.parse_args()

    metadata = analyze_clips(args.clips, job_id=args.job_id)
    write_json_model(args.output, metadata)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
