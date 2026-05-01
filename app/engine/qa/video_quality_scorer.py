from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sample_frames(path: Path, *, sample_count: int = 36) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        if total_frames <= 0:
            return frames
        indexes = np.linspace(0, max(0, total_frames - 1), min(sample_count, total_frames), dtype=int)
        for index in indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if ok:
                frames.append(cv2.resize(frame, (180, 320)))
    finally:
        capture.release()
    return frames


def score_video(path: Path, *, sample_count: int = 36) -> dict[str, Any]:
    frames = _sample_frames(path, sample_count=sample_count)
    if not frames:
        return {
            "video": str(path),
            "score": 0.0,
            "sample_count": 0,
            "error": "no readable frames",
        }

    grays = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames]
    brightness_values = [float(gray.mean()) / 255.0 for gray in grays]
    contrast_values = [float(gray.std()) / 128.0 for gray in grays]
    sharpness_values = [_clamp(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 600.0) for gray in grays]
    white_frames = sum(1 for value in brightness_values if value >= 0.94)
    black_frames = sum(1 for value in brightness_values if value <= 0.04)
    too_dark_frames = sum(1 for value in brightness_values if value <= 0.16)
    too_bright_frames = sum(1 for value in brightness_values if value >= 0.88)

    similarities: list[float] = []
    motion_values: list[float] = []
    for index in range(1, len(grays)):
        diff = cv2.absdiff(grays[index], grays[index - 1])
        motion = float(diff.mean()) / 255.0
        motion_values.append(_clamp(motion / 0.12))
        similarities.append(1.0 - _clamp(motion / 0.18))

    repeated_pairs = sum(1 for similarity in similarities if similarity > 0.96)
    brightness_quality = 1.0 - _clamp((too_dark_frames + too_bright_frames) / len(frames))
    flash_quality = 1.0 - _clamp((white_frames + black_frames) / max(1, len(frames)) * 1.6)
    sharpness_quality = _clamp(sum(sharpness_values) / len(sharpness_values))
    contrast_quality = _clamp(sum(contrast_values) / len(contrast_values))
    repetition_quality = 1.0 - _clamp(repeated_pairs / max(1, len(similarities)))
    motion_balance = _clamp(sum(motion_values) / max(1, len(motion_values)))
    if motion_balance > 0.75:
        motion_quality = 1.0 - ((motion_balance - 0.75) * 0.55)
    elif motion_balance < 0.12:
        motion_quality = motion_balance / 0.12
    else:
        motion_quality = 1.0

    score = (
        flash_quality * 0.23
        + brightness_quality * 0.18
        + sharpness_quality * 0.2
        + contrast_quality * 0.12
        + repetition_quality * 0.15
        + motion_quality * 0.12
    )

    return {
        "video": str(path),
        "score": round(_clamp(score), 4),
        "sample_count": len(frames),
        "metrics": {
            "white_frames": white_frames,
            "black_frames": black_frames,
            "too_dark_frames": too_dark_frames,
            "too_bright_frames": too_bright_frames,
            "repeated_pairs": repeated_pairs,
            "avg_brightness": round(sum(brightness_values) / len(brightness_values), 4),
            "avg_sharpness": round(sum(sharpness_values) / len(sharpness_values), 4),
            "avg_contrast": round(sum(contrast_values) / len(contrast_values), 4),
            "avg_motion": round(motion_balance, 4),
        },
        "subscores": {
            "flash_quality": round(flash_quality, 4),
            "brightness_quality": round(brightness_quality, 4),
            "sharpness_quality": round(sharpness_quality, 4),
            "contrast_quality": round(contrast_quality, 4),
            "repetition_quality": round(repetition_quality, 4),
            "motion_quality": round(motion_quality, 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score an exported video for basic visual quality issues.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--sample-count", type=int, default=36)
    args = parser.parse_args()

    report = score_video(args.video, sample_count=args.sample_count)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
