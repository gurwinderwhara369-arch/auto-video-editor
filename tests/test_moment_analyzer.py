from pathlib import Path

import cv2
import numpy as np

from app.engine.analyzer.moment_analyzer import analyze_clip_moments
from app.engine.core.models import ClipMetadata


def test_moment_analyzer_creates_valid_windows(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10,
        (180, 320),
    )
    for index in range(20):
        frame = np.full((320, 180, 3), 55, dtype=np.uint8)
        cv2.rectangle(frame, (45 + index % 5, 120), (135, 220), (220, 220, 220), -1)
        writer.write(frame)
    writer.release()

    clip = ClipMetadata(
        clip_id="clip_test",
        filename=video.name,
        path=video,
        duration=2.0,
        width=180,
        height=320,
        fps=10,
        overall_score=0.7,
        sharpness_score=0.8,
        brightness_score=0.8,
        motion_score=0.6,
        ai_tags=["needle_work"],
        ai_confidence=0.9,
        best_use="process",
    )

    moments = analyze_clip_moments(clip, max_moments_per_clip=5)

    assert moments
    assert all(0 <= moment.start < moment.end <= clip.duration for moment in moments)
    assert all(1.0 <= moment.crop.crop_zoom <= 2.0 for moment in moments)
    assert all(0 <= moment.crop.crop_x <= 1 for moment in moments)
    assert all(0 <= moment.crop.crop_y <= 1 for moment in moments)
