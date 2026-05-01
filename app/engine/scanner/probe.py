from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.engine.renderer.ffmpeg_runner import FFmpegError, require_binary


def probe_video(path: Path) -> dict:
    require_binary("ffprobe")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    video_stream = next(
        stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"
    )
    audio_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio"),
        None,
    )
    fps = _parse_fps(video_stream.get("r_frame_rate", "0/1"))
    return {
        "duration": float(payload.get("format", {}).get("duration") or video_stream.get("duration") or 0),
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "fps": fps,
        "video_codec": video_stream.get("codec_name"),
        "has_audio": audio_stream is not None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
    }


def _parse_fps(raw: str) -> float:
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return 0.0
        return float(numerator) / denominator_value
    return float(raw)
