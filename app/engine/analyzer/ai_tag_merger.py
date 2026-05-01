from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import ClipMetadata, ClipMetadataSet


def merge_ai_tags(
    metadata: ClipMetadataSet,
    tag_dir: Path,
) -> ClipMetadataSet:
    enriched_clips = [
        _merge_clip(clip, _find_tag_file(tag_dir, clip))
        for clip in metadata.clips
    ]
    return ClipMetadataSet(job_id=metadata.job_id, clips=enriched_clips)


def _find_tag_file(tag_dir: Path, clip: ClipMetadata) -> Path | None:
    candidates = [
        tag_dir / f"{Path(clip.filename).stem}_gemma_tags.json",
        tag_dir / f"{Path(clip.filename).stem}_ai_tags.json",
        tag_dir / f"{clip.clip_id}_gemma_tags.json",
        tag_dir / f"{clip.clip_id}_ai_tags.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted(tag_dir.glob(f"{Path(clip.filename).stem}*.json"))
    return matches[0] if matches else None


def _merge_clip(clip: ClipMetadata, tag_file: Path | None) -> ClipMetadata:
    if tag_file is None:
        return clip

    payload = json.loads(tag_file.read_text(encoding="utf-8"))
    ai_result = payload.get("ai_result", {})
    frames = ai_result.get("frames", [])
    clip_level_tags = list(ai_result.get("clip_level_tags") or [])
    frame_tags = [frame.get("primary_tag") for frame in frames if frame.get("primary_tag")]
    all_tags = _ordered_unique(clip_level_tags + frame_tags)
    best_frame = _best_frame(frames)

    description = ai_result.get("overall_summary") or None
    confidence = None
    best_use = None
    if best_frame:
        description = best_frame.get("description") or description
        confidence = _coerce_float(best_frame.get("confidence"))
        best_use = best_frame.get("best_use")

    return clip.model_copy(
        update={
            "ai_tags": all_tags,
            "ai_description": description,
            "ai_confidence": confidence,
            "best_use": best_use,
            "ai_tag_source": str(tag_file),
        }
    )


def _ordered_unique(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _best_frame(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not frames:
        return None
    usable_frames = [frame for frame in frames if frame.get("best_use") != "unused"] or frames
    return max(usable_frames, key=lambda frame: _coerce_float(frame.get("confidence")) or 0.0)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Gemma AI tag JSON files into clip metadata.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--tag-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata = load_json_model(args.metadata, ClipMetadataSet)
    enriched = merge_ai_tags(metadata, args.tag_dir)
    write_json_model(args.output, enriched)
    tag_counts = Counter(tag for clip in enriched.clips for tag in clip.ai_tags)
    print(f"Wrote {args.output}")
    print(f"Tag counts: {dict(tag_counts)}")


if __name__ == "__main__":
    main()
