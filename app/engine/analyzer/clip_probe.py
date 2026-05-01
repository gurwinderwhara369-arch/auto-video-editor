from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.engine.renderer.ffmpeg_runner import FFmpegError, require_binary


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def list_video_files(clips_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in clips_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def probe_clip(path: Path) -> dict[str, float | int]:
    require_binary("ffprobe")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise FFmpegError(f"No video stream found in {path}")
    stream = streams[0]
    fps = _parse_fps(stream.get("r_frame_rate", "0/1"))
    duration = float(stream.get("duration") or 0)
    return {
        "duration": duration,
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
    }


def _parse_fps(raw: str) -> float:
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return 0.0
        return float(numerator) / denominator_value
    return float(raw)
