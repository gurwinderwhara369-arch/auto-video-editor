from __future__ import annotations

from pathlib import Path

import cv2


def score_brightness(path: Path, *, max_frames: int = 24) -> float:
    capture = cv2.VideoCapture(str(path))
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, total_frames // max_frames)
        luminance_values: list[float] = []
        frame_index = 0
        while len(luminance_values) < max_frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            luminance_values.append(float(gray.mean()) / 255.0)
            frame_index += step
        if not luminance_values:
            return 0.0
        brightness = sum(luminance_values) / len(luminance_values)
        if brightness < 0.5:
            return max(0.0, brightness / 0.5)
        return max(0.0, (1.0 - brightness) / 0.5)
    finally:
        capture.release()
