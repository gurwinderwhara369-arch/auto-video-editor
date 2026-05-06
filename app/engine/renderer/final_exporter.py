from __future__ import annotations

import shutil
from pathlib import Path

from app.engine.core.models import Timeline
from app.engine.renderer.effects import build_effect_filters
from app.engine.renderer.ffmpeg_runner import run_ffmpeg


def _render_segment(
    timeline: Timeline,
    segment_index: int,
    segment_path: Path,
    temp_dir: Path,
    *,
    debug: bool = False,
) -> Path:
    segment = timeline.timeline[segment_index]
    duration = segment.timeline_end - segment.timeline_start
    source_duration = max(0.05, segment.source_end - segment.source_start)
    output = temp_dir / f"segment_{segment_index:03d}.mp4"
    filters = build_effect_filters(
        segment.effect,
        timeline.global_style,
        timeline.resolution,
        segment_duration=duration,
        fps=timeline.fps,
        crop=segment.crop,
    )
    flash_duration = segment.transition_out.duration or 0.15
    if segment.transition_out.type == "white_flash" and duration > flash_duration:
        filters.append(
            f"fade=t=out:st={duration - flash_duration:.3f}:d={flash_duration:.3f}:color=white"
        )
    elif segment.transition_out.type == "black_flash" and duration > flash_duration:
        filters.append(
            f"fade=t=out:st={duration - flash_duration:.3f}:d={flash_duration:.3f}:color=black"
        )
    elif segment.transition_out.type == "fade" and duration > flash_duration:
        filters.append(f"fade=t=out:st={duration - flash_duration:.3f}:d={flash_duration:.3f}")
    elif segment.transition_out.type == "glitch":
        filters.append("hue=s=1.35,eq=contrast=1.16")
    elif segment.transition_out.type in {"white_hit", "black_hit", "flash_hit", "white_slam", "black_slam", "freeze_cut"}:
        hit_duration = min(flash_duration, max(1 / timeline.fps, duration * 0.35))
        color = "black" if segment.transition_out.type in {"black_hit", "black_slam"} else "white"
        filters.append(f"fade=t=out:st={duration - hit_duration:.3f}:d={hit_duration:.3f}:color={color}")
        if segment_index > 0 and segment.transition_out.type == "flash_hit" and duration > hit_duration * 2:
            filters.append(f"fade=t=in:st=0:d={hit_duration:.3f}:color=white")
    elif segment.transition_out.type in {"red_hit", "invert_hit", "blur_hit", "strobe_hit", "red_slam", "glitch_slam", "blur_push", "panel_snap", "beat_stutter"}:
        hit_duration = min(flash_duration, max(1 / timeline.fps, duration * 0.35))
        hit_start = max(0.0, duration - hit_duration)
        if segment.transition_out.type in {"red_hit", "red_slam"}:
            filters.append(
                "colorchannelmixer=rr=1.35:gg=0.72:bb=0.72:"
                f"enable='gte(t,{hit_start:.3f})'"
            )
        elif segment.transition_out.type in {"invert_hit", "glitch_slam", "panel_snap", "beat_stutter"}:
            filters.append(f"negate=enable='gte(t,{hit_start:.3f})'")
        elif segment.transition_out.type in {"blur_hit", "blur_push"}:
            filters.append(f"boxblur=8:2:enable='gte(t,{hit_start:.3f})'")
        elif segment.transition_out.type == "strobe_hit":
            filters.append(
                "eq=brightness=0.28:contrast=1.25:"
                f"enable='gte(t,{hit_start:.3f})*lt(mod(t,0.066),0.033)'"
            )
    filters.append(f"trim=duration={duration:.3f},setpts=PTS-STARTPTS")
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{segment.source_start:.3f}",
        "-t",
        f"{source_duration:.3f}",
        "-i",
        str(segment_path),
        "-vf",
        ",".join(filters),
        "-an",
        "-r",
        str(timeline.fps),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    run_ffmpeg(cmd, debug=debug)
    return output

def render_timeline(
    timeline: Timeline,
    *,
    temp_dir: Path,
    debug: bool = False,
    clean: bool = True,
) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    timeline.output_file.parent.mkdir(parents=True, exist_ok=True)

    segment_files: list[Path] = []
    for index, segment in enumerate(timeline.timeline):
        segment_files.append(
            _render_segment(timeline, index, Path(segment.source_file), temp_dir, debug=debug)
        )

    concat_file = temp_dir / "segments.txt"
    with concat_file.open("w", encoding="utf-8") as handle:
        for segment_file in segment_files:
            handle.write(f"file '{segment_file.resolve()}'\n")

    video_only = temp_dir / "video_only.mp4"
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(video_only),
        ],
        debug=debug,
    )

    audio_duration = timeline.audio.end - timeline.audio.start
    audio_fade_out_start = max(0.0, audio_duration - 0.18)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_only),
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
            "copy",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "256k",
            "-af",
            f"afade=t=in:st=0:d=0.05,afade=t=out:st={audio_fade_out_start:.3f}:d=0.18,alimiter=limit=0.95",
            "-shortest",
            "-movflags",
            "+faststart",
            str(timeline.output_file),
        ],
        debug=debug,
    )

    if clean:
        shutil.rmtree(temp_dir, ignore_errors=True)
