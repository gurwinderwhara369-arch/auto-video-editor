from __future__ import annotations

import shutil
import subprocess


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg/ffprobe command fails."""


def require_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise FFmpegError(
            f"{binary} was not found. In Codespaces, rebuild the devcontainer or run: "
            "sudo apt-get update && sudo apt-get install -y ffmpeg"
        )


def run_ffmpeg(cmd: list[str], *, debug: bool = False) -> None:
    require_binary(cmd[0])
    if debug:
        print(" ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise FFmpegError(
            f"Command failed with exit code {result.returncode}: {' '.join(cmd)}\n"
            f"{result.stderr.strip()}"
        )
