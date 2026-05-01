from __future__ import annotations

from pathlib import Path

import cv2


def score_sharpness(path: Path, *, max_frames: int = 24) -> float:
    capture = cv2.VideoCapture(str(path))
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, total_frames // max_frames)
        values: list[float] = []
        frame_index = 0
        while len(values) < max_frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            values.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            frame_index += step
        if not values:
            return 0.0
        average = sum(values) / len(values)
        return max(0.0, min(1.0, average / 600.0))
    finally:
        capture.release()
