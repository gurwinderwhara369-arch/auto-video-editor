from __future__ import annotations

import math
import shutil
from pathlib import Path

import cv2
import numpy as np

from app.engine.core.models import Resolution, Timeline, TimelineSegment
from app.engine.renderer.ffmpeg_runner import run_ffmpeg


CANVAS_EFFECTS = (
    "blur_wall",
    "freeze_punch",
    "echo_trail",
    "split_panel",
    "beat_flash_stack",
    "cutout_pop",
    "duplicate_subject_echo",
    "zoom_burst",
    "frame_hold",
    "background_pulse",
    "text_flash",
    "edge_glow",
    "film_damage",
)


def render_canvas_timeline(
    timeline: Timeline,
    *,
    temp_dir: Path,
    debug: bool = False,
    clean: bool = True,
) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    timeline.output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_video = temp_dir / "canvas_video.mp4"
    frame_size = (timeline.resolution.width, timeline.resolution.height)
    writer = cv2.VideoWriter(
        str(temp_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        timeline.fps,
        frame_size,
    )
    if not writer.isOpened():
        raise RuntimeError("Could not open OpenCV VideoWriter for canvas render")

    try:
        for segment in timeline.timeline:
            _render_canvas_segment(writer, timeline.resolution, timeline.fps, segment)
    finally:
        writer.release()

    audio_duration = timeline.audio.end - timeline.audio.start
    audio_fade_out_start = max(0.0, audio_duration - 0.18)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(temp_video),
            "-ss",
            f"{timeline.audio.start:.3f}",
            "-t",
            f"{audio_duration:.3f}",
            "-i",
            str(timeline.audio.file),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "256k",
            "-af",
            f"afade=t=in:st=0:d=0.04,afade=t=out:st={audio_fade_out_start:.3f}:d=0.18,alimiter=limit=0.95",
            "-shortest",
            "-movflags",
            "+faststart",
            str(timeline.output_file),
        ],
        debug=debug,
    )

    if clean:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _render_canvas_segment(
    writer: cv2.VideoWriter,
    resolution: Resolution,
    fps: int,
    segment: TimelineSegment,
) -> None:
    capture = cv2.VideoCapture(str(segment.source_file))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open source clip for canvas render: {segment.source_file}")

    output_frames = max(1, int(round(segment.duration * fps)))
    source_duration = max(0.001, segment.source_end - segment.source_start)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or fps
    effect = _canvas_effect_for_segment(segment)
    previous_frames: list[np.ndarray] = []
    freeze_frame: np.ndarray | None = None
    last_frame: np.ndarray | None = None

    try:
        for frame_index in range(output_frames):
            local_t = frame_index / max(1, output_frames - 1)
            source_time = segment.source_start + (source_duration * local_t)
            if effect in {"freeze_punch", "frame_hold"} and (effect == "frame_hold" or local_t < 0.26):
                if freeze_frame is None:
                    freeze_frame = _read_frame(capture, segment.source_start, source_fps)
                frame = freeze_frame
            else:
                frame = _read_frame(capture, source_time, source_fps)
            if frame is None:
                frame = last_frame
            if frame is None:
                frame = np.zeros((resolution.height, resolution.width, 3), dtype=np.uint8)
            last_frame = frame

            canvas = _compose_base(frame, resolution)
            if effect == "blur_wall":
                canvas = _effect_blur_wall(frame, resolution, local_t)
            elif effect == "freeze_punch":
                canvas = _effect_freeze_punch(canvas, local_t)
            elif effect in {"echo_trail", "duplicate_subject_echo"}:
                canvas = _effect_echo_trail(canvas, previous_frames, local_t)
            elif effect == "split_panel":
                canvas = _effect_split_panel(frame, resolution, local_t)
            elif effect == "beat_flash_stack":
                canvas = _effect_beat_flash_stack(canvas, local_t)
            elif effect == "cutout_pop":
                canvas = _effect_cutout_pop(frame, resolution, local_t)
            elif effect == "zoom_burst":
                canvas = _effect_zoom_burst(canvas, local_t)
            elif effect == "frame_hold":
                canvas = _effect_frame_hold(canvas, local_t)
            elif effect == "background_pulse":
                canvas = _effect_background_pulse(frame, resolution, local_t)
            elif effect == "text_flash":
                canvas = _effect_text_flash(canvas, local_t)
            elif effect == "edge_glow":
                canvas = _effect_edge_glow(canvas, local_t)
            elif effect == "film_damage":
                canvas = _effect_film_damage(canvas, frame_index)

            canvas = _apply_visual_events(canvas, segment, local_t)
            canvas = _apply_transition_hit(canvas, segment, local_t)

            canvas = _grade(canvas)
            previous_frames.append(canvas.copy())
            previous_frames = previous_frames[-4:]
            writer.write(canvas)
    finally:
        capture.release()


def _read_frame(capture: cv2.VideoCapture, time_seconds: float, fps: float) -> np.ndarray | None:
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(time_seconds * fps)))
    ok, frame = capture.read()
    return frame if ok else None


def _canvas_effect_for_segment(segment: TimelineSegment) -> str:
    existing = segment.effect.metadata.get("canvas_effect") if segment.effect.metadata else None
    if existing in CANVAS_EFFECTS:
        return str(existing)
    event_types = {event.type for event in segment.visual_events}
    event_map = {
        "panel_split": "split_panel",
        "freeze": "freeze_punch",
        "cutout_overlay": "cutout_pop",
        "echo_trail": "duplicate_subject_echo",
        "flash_stack": "beat_flash_stack",
        "zoom_burst": "zoom_burst",
        "background_pulse": "background_pulse",
        "text_zone": "text_flash",
        "shake_hit": "edge_glow",
        "blur_wall": "blur_wall",
    }
    for event_type, canvas_effect in event_map.items():
        if event_type in event_types:
            return canvas_effect
    if segment.segment_index >= 0:
        cycle = ("blur_wall", "freeze_punch", "echo_trail", "split_panel", "beat_flash_stack")
        if segment.effect.type in {"rgb_glitch", "glitch", "strobe", "pixel_punch"}:
            return "beat_flash_stack"
        if segment.effect.type in {"impact_zoom", "speed_ramp", "freeze_punch"}:
            return "freeze_punch"
        if segment.effect.type in {"motion_blur", "whip_pan", "rotate_shake", "duplicate_subject_echo"}:
            return "echo_trail"
        if segment.effect.type in CANVAS_EFFECTS:
            return segment.effect.type
        return cycle[segment.segment_index % len(cycle)]
    return "blur_wall"


def _compose_base(frame: np.ndarray, resolution: Resolution) -> np.ndarray:
    background = _cover(frame, resolution.width, resolution.height)
    background = cv2.GaussianBlur(background, (0, 0), 28)
    background = cv2.convertScaleAbs(background, alpha=0.72, beta=-18)
    foreground = _cover(frame, resolution.width, resolution.height)
    return cv2.addWeighted(background, 0.34, foreground, 0.88, 0)


def _effect_blur_wall(frame: np.ndarray, resolution: Resolution, local_t: float) -> np.ndarray:
    background = _cover(frame, resolution.width, resolution.height)
    background = cv2.GaussianBlur(background, (0, 0), 36)
    background = cv2.convertScaleAbs(background, alpha=0.8, beta=-24)
    foreground = _contain(frame, int(resolution.width * 0.88), resolution.height)
    zoom = 1.0 + 0.035 * math.sin(local_t * math.pi)
    foreground = _zoom(foreground, zoom)
    canvas = background.copy()
    x = (resolution.width - foreground.shape[1]) // 2
    y = (resolution.height - foreground.shape[0]) // 2
    _paste(canvas, foreground, x, y)
    return canvas


def _effect_freeze_punch(canvas: np.ndarray, local_t: float) -> np.ndarray:
    if local_t < 0.32:
        zoom = 1.0 + (0.22 * math.sin((local_t / 0.32) * math.pi / 2))
        canvas = _zoom(canvas, zoom, output_size=(canvas.shape[1], canvas.shape[0]))
    if local_t < 0.10:
        alpha = 0.48 * (1.0 - local_t / 0.10)
        canvas = _solid_hit(canvas, (255, 255, 255), alpha)
    return canvas


def _effect_echo_trail(canvas: np.ndarray, previous_frames: list[np.ndarray], local_t: float) -> np.ndarray:
    output = canvas.copy()
    for idx, previous in enumerate(reversed(previous_frames[-3:]), start=1):
        shift = int((18 + idx * 11) * math.sin(local_t * math.pi))
        transform = np.float32([[1, 0, -shift], [0, 1, shift // 3]])
        shifted = cv2.warpAffine(previous, transform, (canvas.shape[1], canvas.shape[0]), borderMode=cv2.BORDER_REFLECT)
        output = cv2.addWeighted(output, 1.0, shifted, 0.16 / idx, 0)
    return output


def _effect_split_panel(frame: np.ndarray, resolution: Resolution, local_t: float) -> np.ndarray:
    canvas = np.zeros((resolution.height, resolution.width, 3), dtype=np.uint8)
    panel_w = resolution.width // 3
    offsets = [-28, 0, 28]
    for index in range(3):
        panel = _cover(frame, panel_w + 42, resolution.height)
        x_shift = int(offsets[index] * math.sin(local_t * math.pi))
        panel = panel[:, max(0, 21 + x_shift) : max(0, 21 + x_shift) + panel_w]
        if panel.shape[1] != panel_w:
            panel = cv2.resize(panel, (panel_w, resolution.height))
        x = index * panel_w
        canvas[:, x : x + panel_w] = panel
    if resolution.width - panel_w * 3:
        canvas[:, panel_w * 3 :] = canvas[:, panel_w * 3 - 1 : panel_w * 3]
    return canvas


def _effect_beat_flash_stack(canvas: np.ndarray, local_t: float) -> np.ndarray:
    output = canvas.copy()
    flash_points = (0.0, 0.22, 0.5, 0.78)
    for point in flash_points:
        distance = abs(local_t - point)
        if distance < 0.045:
            alpha = 0.45 * (1 - distance / 0.045)
            color = (255, 255, 255) if point in {0.0, 0.5} else (30, 30, 210)
            output = _solid_hit(output, color, alpha)
    shift = int(8 * math.sin(local_t * math.pi * 8))
    if abs(shift) > 2:
        b, g, r = cv2.split(output)
        r = np.roll(r, shift, axis=1)
        b = np.roll(b, -shift, axis=1)
        output = cv2.merge([b, g, r])
    return output


def _effect_cutout_pop(frame: np.ndarray, resolution: Resolution, local_t: float) -> np.ndarray:
    background = _cover(frame, resolution.width, resolution.height)
    background = cv2.GaussianBlur(background, (0, 0), 42)
    background = cv2.convertScaleAbs(background, alpha=0.68, beta=-28)
    foreground = _cover(frame, resolution.width, resolution.height)
    scale = 0.9 + 0.12 * math.sin(min(1.0, local_t * 2.2) * math.pi / 2)
    foreground = _zoom(foreground, scale, output_size=(resolution.width, resolution.height))
    mask = _soft_center_mask(resolution.width, resolution.height, local_t)
    output = _alpha_blend(background, foreground, mask)
    if local_t < 0.14:
        output = _solid_hit(output, (255, 255, 255), 0.18 * (1 - local_t / 0.14))
    return output


def _effect_zoom_burst(canvas: np.ndarray, local_t: float) -> np.ndarray:
    zoom = 1.0 + 0.26 * math.sin(min(1.0, local_t * 1.45) * math.pi / 2)
    output = _zoom(canvas, zoom, output_size=(canvas.shape[1], canvas.shape[0]))
    ghost = cv2.GaussianBlur(output, (0, 0), 9)
    alpha = 0.22 * max(0.0, 1.0 - local_t)
    return cv2.addWeighted(output, 1.0, ghost, alpha, 0)


def _effect_frame_hold(canvas: np.ndarray, local_t: float) -> np.ndarray:
    output = canvas.copy()
    if local_t < 0.22:
        output = _zoom(output, 1.0 + 0.12 * (local_t / 0.22), output_size=(output.shape[1], output.shape[0]))
        output = _solid_hit(output, (245, 245, 245), 0.22 * (1 - local_t / 0.22))
    return output


def _effect_background_pulse(frame: np.ndarray, resolution: Resolution, local_t: float) -> np.ndarray:
    output = _effect_blur_wall(frame, resolution, local_t)
    pulse = 0.18 * (0.5 + 0.5 * math.sin(local_t * math.pi * 4))
    return _solid_hit(output, (28, 20, 180), pulse)


def _effect_text_flash(canvas: np.ndarray, local_t: float) -> np.ndarray:
    output = canvas.copy()
    h, w = output.shape[:2]
    band_h = max(90, h // 13)
    y = int(h * (0.18 + 0.02 * math.sin(local_t * math.pi)))
    overlay = output.copy()
    cv2.rectangle(overlay, (0, y), (w, y + band_h), (0, 0, 0), -1)
    output = cv2.addWeighted(output, 0.78, overlay, 0.22, 0)
    text = "INK SESSION"
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = 1.1
    thickness = 2
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    x = max(18, (w - text_size[0]) // 2)
    baseline = y + (band_h + text_size[1]) // 2
    cv2.putText(output, text, (x, baseline), font, scale, (245, 245, 245), thickness, cv2.LINE_AA)
    if local_t < 0.08:
        output = _solid_hit(output, (255, 255, 255), 0.26 * (1 - local_t / 0.08))
    return output


def _effect_edge_glow(canvas: np.ndarray, local_t: float) -> np.ndarray:
    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 150)
    glow = cv2.GaussianBlur(edges, (0, 0), 4)
    colored = np.zeros_like(canvas)
    colored[:, :, 2] = glow
    colored[:, :, 1] = (glow * 0.35).astype(np.uint8)
    alpha = 0.22 + 0.16 * math.sin(local_t * math.pi * 3)
    return cv2.addWeighted(canvas, 1.0, colored, alpha, 0)


def _effect_film_damage(canvas: np.ndarray, frame_index: int) -> np.ndarray:
    rng = np.random.default_rng(frame_index)
    noise = rng.normal(0, 10, canvas.shape).astype(np.int16)
    output = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    h, w = output.shape[:2]
    for offset in (frame_index * 37 % w, frame_index * 53 % w):
        cv2.line(output, (offset, 0), (offset, h), (220, 220, 220), 1)
    return output


def _grade(frame: np.ndarray) -> np.ndarray:
    frame = cv2.convertScaleAbs(frame, alpha=1.12, beta=-6)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= 1.12
    hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
    frame = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    blur = cv2.GaussianBlur(frame, (0, 0), 1.1)
    return cv2.addWeighted(frame, 1.28, blur, -0.28, 0)


def _apply_visual_events(canvas: np.ndarray, segment: TimelineSegment, local_t: float) -> np.ndarray:
    output = canvas
    duration = max(0.001, segment.duration)
    for event in segment.visual_events:
        event_start = event.start / duration
        event_end = (event.end if event.end is not None else event.start + 0.12) / duration
        if not (event_start <= local_t <= event_end):
            continue
        event_span = max(0.001, event_end - event_start)
        event_t = (local_t - event_start) / event_span
        if event.type == "flash_stack":
            output = _solid_hit(output, (255, 255, 255), 0.38 * event.intensity * (1 - min(1.0, event_t)))
        elif event.type == "background_pulse":
            output = _solid_hit(output, (32, 22, 190), 0.16 * event.intensity)
        elif event.type == "shake_hit":
            shift = int(22 * event.intensity * math.sin(event_t * math.pi * 3))
            output = np.roll(output, shift, axis=1)
        elif event.type == "zoom_burst":
            output = _zoom(output, 1.0 + 0.08 * event.intensity, output_size=(output.shape[1], output.shape[0]))
    return output


def _apply_transition_hit(canvas: np.ndarray, segment: TimelineSegment, local_t: float) -> np.ndarray:
    transition = segment.transition_out.type
    if transition in {"cut", "fade"} or local_t < 0.88:
        return canvas
    strength = (local_t - 0.88) / 0.12
    if transition in {"white_slam", "white_hit", "flash_hit"}:
        return _solid_hit(canvas, (255, 255, 255), 0.52 * strength)
    if transition in {"black_slam", "black_hit"}:
        return _solid_hit(canvas, (0, 0, 0), 0.58 * strength)
    if transition in {"red_slam", "red_hit"}:
        return _solid_hit(canvas, (25, 20, 210), 0.45 * strength)
    if transition in {"glitch_slam", "glitch", "beat_stutter"}:
        shifted = np.roll(canvas, int(18 * strength), axis=1)
        return cv2.addWeighted(canvas, 0.76, shifted, 0.24, 0)
    if transition in {"blur_push", "blur_hit"}:
        return cv2.GaussianBlur(canvas, (0, 0), 1 + 8 * strength)
    if transition == "panel_snap":
        return _effect_split_panel(canvas, Resolution(width=canvas.shape[1], height=canvas.shape[0]), strength)
    if transition == "freeze_cut":
        return _solid_hit(canvas, (245, 245, 245), 0.34 * strength)
    return canvas


def _cover(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = max(width / w, height / h)
    resized = cv2.resize(frame, (max(width, int(w * scale)), max(height, int(h * scale))))
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y : y + height, x : x + width]


def _contain(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))


def _zoom(frame: np.ndarray, zoom: float, output_size: tuple[int, int] | None = None) -> np.ndarray:
    h, w = frame.shape[:2]
    out_w, out_h = output_size or (w, h)
    scaled = cv2.resize(frame, (max(out_w, int(w * zoom)), max(out_h, int(h * zoom))))
    y = (scaled.shape[0] - out_h) // 2
    x = (scaled.shape[1] - out_w) // 2
    return scaled[y : y + out_h, x : x + out_w]


def _paste(canvas: np.ndarray, layer: np.ndarray, x: int, y: int) -> None:
    h, w = layer.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.shape[1], x + w), min(canvas.shape[0], y + h)
    lx0, ly0 = x0 - x, y0 - y
    canvas[y0:y1, x0:x1] = layer[ly0 : ly0 + (y1 - y0), lx0 : lx0 + (x1 - x0)]


def _solid_hit(frame: np.ndarray, color: tuple[int, int, int], alpha: float) -> np.ndarray:
    overlay = np.full_like(frame, color)
    return cv2.addWeighted(frame, 1 - alpha, overlay, alpha, 0)


def _soft_center_mask(width: int, height: int, local_t: float) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.float32)
    radius_x = int(width * (0.34 + 0.04 * math.sin(local_t * math.pi)))
    radius_y = int(height * 0.36)
    cv2.ellipse(mask, (width // 2, height // 2), (radius_x, radius_y), 0, 0, 360, 1.0, -1)
    return cv2.GaussianBlur(mask, (0, 0), 22)


def _alpha_blend(background: np.ndarray, foreground: np.ndarray, mask: np.ndarray) -> np.ndarray:
    alpha = np.clip(mask[:, :, None], 0.0, 1.0)
    return np.clip(background.astype(np.float32) * (1 - alpha) + foreground.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
