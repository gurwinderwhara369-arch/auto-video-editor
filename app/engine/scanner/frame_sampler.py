from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class FrameStat:
    time: float
    brightness: float
    saturation: float
    contrast: float
    sharpness: float
    motion: float
    hist_diff: float
    frame_diff: float


def scan_frame_stats(path: Path, *, sample_every_n_frames: int = 1, max_width: int = 320) -> list[FrameStat]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Could not open reference video: {path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    previous_hist = None
    previous_gray = None
    stats: list[FrameStat] = []
    frame_index = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % sample_every_n_frames != 0:
                frame_index += 1
                continue

            frame = _resize_for_scan(frame, max_width=max_width)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist)

            hist_diff = 0.0
            if previous_hist is not None:
                hist_diff = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA))

            frame_diff = 0.0
            motion = 0.0
            if previous_gray is not None:
                diff = cv2.absdiff(gray, previous_gray)
                frame_diff = float(diff.mean()) / 255.0
                motion = min(1.0, frame_diff / 0.18)

            stats.append(
                FrameStat(
                    time=round(frame_index / fps, 4),
                    brightness=float(gray.mean()) / 255.0,
                    saturation=float(hsv[:, :, 1].mean()) / 255.0,
                    contrast=float(gray.std()) / 128.0,
                    sharpness=min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 700.0),
                    motion=motion,
                    hist_diff=hist_diff,
                    frame_diff=frame_diff,
                )
            )
            previous_hist = hist
            previous_gray = gray
            frame_index += 1
    finally:
        capture.release()

    return stats


def _resize_for_scan(frame: np.ndarray, *, max_width: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    return cv2.resize(frame, (max_width, max(1, int(height * scale))))
