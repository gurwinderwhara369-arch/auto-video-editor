from __future__ import annotations

from pathlib import Path

import cv2


def score_motion(path: Path, *, max_frames: int = 36) -> float:
    capture = cv2.VideoCapture(str(path))
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(1, total_frames // max_frames)
        previous_gray = None
        diffs: list[float] = []
        frame_index = 0
        while len(diffs) < max_frames:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                break
            small = cv2.resize(frame, (160, 284))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if previous_gray is not None:
                diff = cv2.absdiff(gray, previous_gray)
                diffs.append(float(diff.mean()) / 255.0)
            previous_gray = gray
            frame_index += step
        if not diffs:
            return 0.0
        average = sum(diffs) / len(diffs)
        return max(0.0, min(1.0, average / 0.12))
    finally:
        capture.release()
