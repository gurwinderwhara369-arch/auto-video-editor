from pathlib import Path

import cv2
import numpy as np

from app.engine.qa.video_quality_scorer import score_video


def _write_video(path: Path, frames: list[np.ndarray]) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (90, 160))
    for frame in frames:
        writer.write(frame)
    writer.release()


def test_video_quality_scorer_penalizes_flat_white_frames(tmp_path: Path) -> None:
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good_frames = []
    for index in range(12):
        frame = np.full((160, 90, 3), 70 + index * 3, dtype=np.uint8)
        cv2.rectangle(frame, (20 + index % 4, 35), (70, 115), (180, 180, 180), -1)
        good_frames.append(frame)
    bad_frames = [np.full((160, 90, 3), 255, dtype=np.uint8) for _ in range(12)]
    _write_video(good, good_frames)
    _write_video(bad, bad_frames)

    good_score = score_video(good, sample_count=8)
    bad_score = score_video(bad, sample_count=8)

    assert good_score["score"] > bad_score["score"]
    assert bad_score["metrics"]["white_frames"] > 0
