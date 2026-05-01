from __future__ import annotations

from pathlib import Path

from app.engine.renderer.ffmpeg_runner import run_ffmpeg


def extract_audio(reference_video: Path, output_audio: Path, *, debug: bool = False) -> Path:
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(reference_video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(output_audio),
        ],
        debug=debug,
    )
    return output_audio


def make_scan_proxy(reference_video: Path, output_video: Path, *, debug: bool = False) -> Path:
    output_video.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(reference_video),
            "-an",
            "-vf",
            "scale='min(640,iw)':-2",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output_video),
        ],
        debug=debug,
    )
    return output_video
