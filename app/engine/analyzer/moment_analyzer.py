from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import ClipMetadata, ClipMetadataSet, CropMetadata, MomentMetadata, MomentMetadataSet

WINDOW_SIZES = (0.35, 0.5, 0.75, 1.2)
MAX_STARTS_PER_WINDOW_SIZE = 8


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _read_frame(capture: cv2.VideoCapture, time_seconds: float, fps: float) -> np.ndarray | None:
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(time_seconds * fps)))
    ok, frame = capture.read()
    return frame if ok else None


def _sample_window_frames(
    capture: cv2.VideoCapture,
    *,
    start: float,
    end: float,
    fps: float,
) -> list[np.ndarray]:
    sample_times = [start, (start + end) / 2, max(start, end - (1 / max(fps, 1.0)))]
    frames = [_read_frame(capture, sample_time, fps) for sample_time in sample_times]
    return [frame for frame in frames if frame is not None]


def _brightness_score(gray: np.ndarray) -> float:
    brightness = float(gray.mean()) / 255.0
    if brightness < 0.5:
        return _clamp(brightness / 0.5)
    return _clamp((1.0 - brightness) / 0.5)


def _sharpness_score(gray: np.ndarray) -> float:
    return _clamp(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 600.0)


def _motion_score(grays: list[np.ndarray]) -> float:
    if len(grays) < 2:
        return 0.0
    diffs = [float(cv2.absdiff(grays[index], grays[index - 1]).mean()) / 255.0 for index in range(1, len(grays))]
    return _clamp((sum(diffs) / len(diffs)) / 0.12)


def _stability_score(grays: list[np.ndarray]) -> float:
    if len(grays) < 2:
        return 0.75
    diffs = [float(cv2.absdiff(grays[index], grays[index - 1]).mean()) / 255.0 for index in range(1, len(grays))]
    return _clamp(1.0 - ((sum(diffs) / len(diffs)) / 0.18))


def _crop_from_frames(frames: list[np.ndarray], *, source_width: int, source_height: int) -> CropMetadata:
    if not frames:
        return CropMetadata()

    heatmap: np.ndarray | None = None
    previous_gray: np.ndarray | None = None
    for frame in frames:
        small = cv2.resize(frame, (180, 320))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 65, 150).astype(np.float32) / 255.0
        laplacian = cv2.convertScaleAbs(cv2.Laplacian(gray, cv2.CV_16S, ksize=3)).astype(np.float32) / 255.0
        motion = np.zeros_like(edges)
        if previous_gray is not None:
            motion = cv2.absdiff(gray, previous_gray).astype(np.float32) / 255.0
        frame_heat = edges * 0.45 + laplacian * 0.35 + motion * 0.20
        heatmap = frame_heat if heatmap is None else heatmap + frame_heat
        previous_gray = gray

    if heatmap is None or float(heatmap.max()) <= 0:
        return CropMetadata()

    heatmap = cv2.GaussianBlur(heatmap, (17, 17), 0)
    ys, xs = np.indices(heatmap.shape)
    weights = heatmap + 1e-6
    total = float(weights.sum())
    center_x = float((xs * weights).sum() / total) / max(1, heatmap.shape[1] - 1)
    center_y = float((ys * weights).sum() / total) / max(1, heatmap.shape[0] - 1)

    vertical_ratio = source_height / max(1, source_width)
    mostly_vertical = 1.65 <= vertical_ratio <= 1.9
    confidence = _clamp(float(heatmap.std()) * 6.0)
    zoom = 1.03 if mostly_vertical else 1.12
    if confidence > 0.45:
        zoom += 0.05

    return CropMetadata(
        crop_x=_clamp(center_x, 0.18, 0.82),
        crop_y=_clamp(center_y, 0.18, 0.82),
        crop_zoom=_clamp(zoom, 1.0, 1.25),
        framing_confidence=confidence,
    )


def _moment_type(clip: ClipMetadata, *, motion: float, stability: float, sharpness: float) -> str:
    tags = set(clip.ai_tags)
    if "final_reveal" in tags and stability >= 0.45:
        return "reveal_candidate"
    if "stencil" in tags or "artist_client" in tags:
        return "intro"
    if "wiping" in tags and motion >= 0.35:
        return "wiping"
    if "needle_work" in tags and motion >= 0.25:
        return "needle_work"
    if "closeup_detail" in tags or (sharpness >= 0.55 and stability >= 0.45):
        return "detail"
    if motion >= 0.65:
        return "transition"
    return "process"


def _score_moment(
    clip: ClipMetadata,
    *,
    sharpness: float,
    brightness: float,
    motion: float,
    stability: float,
    moment_type: str,
) -> float:
    tag_bonus = 0.08 if moment_type in {"needle_work", "wiping", "detail", "reveal_candidate"} else 0.03
    reveal_bonus = 0.08 if moment_type == "reveal_candidate" else 0.0
    score = (
        sharpness * 0.32
        + brightness * 0.22
        + motion * 0.22
        + stability * 0.16
        + tag_bonus
        + reveal_bonus
        + clip.overall_score * 0.08
    )
    return _clamp(score)


def analyze_clip_moments(clip: ClipMetadata, *, max_moments_per_clip: int = 18) -> list[MomentMetadata]:
    capture = cv2.VideoCapture(str(clip.path))
    moments: list[MomentMetadata] = []
    try:
        for window_size in WINDOW_SIZES:
            if clip.duration < window_size:
                continue
            max_start = max(0.0, clip.duration - window_size)
            start_count = max(1, min(MAX_STARTS_PER_WINDOW_SIZE, int(max_start / max(0.45, window_size)) + 1))
            starts = [0.0] if start_count == 1 else np.linspace(0.0, max_start, start_count)
            for start_value in starts:
                start = float(start_value)
                end = min(clip.duration, start + window_size)
                frames = _sample_window_frames(capture, start=start, end=end, fps=clip.fps)
                if frames:
                    grays = [cv2.cvtColor(cv2.resize(frame, (160, 284)), cv2.COLOR_BGR2GRAY) for frame in frames]
                    sharpness = sum(_sharpness_score(gray) for gray in grays) / len(grays)
                    brightness = sum(_brightness_score(gray) for gray in grays) / len(grays)
                    motion = _motion_score(grays)
                    stability = _stability_score(grays)
                    moment_type = _moment_type(clip, motion=motion, stability=stability, sharpness=sharpness)
                    score = _score_moment(
                        clip,
                        sharpness=sharpness,
                        brightness=brightness,
                        motion=motion,
                        stability=stability,
                        moment_type=moment_type,
                    )
                    crop = _crop_from_frames(frames, source_width=clip.width, source_height=clip.height)
                    moments.append(
                        MomentMetadata(
                            moment_id=f"{clip.clip_id}_{len(moments) + 1:04d}",
                            clip_id=clip.clip_id,
                            source_file=clip.path,
                            start=round(start, 3),
                            end=round(end, 3),
                            duration=round(end - start, 3),
                            moment_type=moment_type,
                            score=score,
                            sharpness_score=sharpness,
                            brightness_score=brightness,
                            motion_score=motion,
                            stability_score=stability,
                            crop=crop,
                        )
                    )
    finally:
        capture.release()

    moments.sort(key=lambda moment: (moment.score, moment.duration), reverse=True)
    return moments[:max_moments_per_clip]


def analyze_moments(metadata: ClipMetadataSet, *, max_moments_per_clip: int = 18) -> MomentMetadataSet:
    moments: list[MomentMetadata] = []
    for clip in metadata.clips:
        print(f"Analyzing moments for {clip.clip_id} {clip.filename}", flush=True)
        moments.extend(analyze_clip_moments(clip, max_moments_per_clip=max_moments_per_clip))
    return MomentMetadataSet(job_id=metadata.job_id, moments=moments)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze best source moments inside tattoo clips.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-moments-per-clip", type=int, default=18)
    args = parser.parse_args()

    metadata = load_json_model(args.metadata, ClipMetadataSet)
    moments = analyze_moments(metadata, max_moments_per_clip=args.max_moments_per_clip)
    write_json_model(args.output, moments)
    print(f"Wrote {args.output}")
    print(f"Moments: {len(moments.moments)}")


if __name__ == "__main__":
    main()
