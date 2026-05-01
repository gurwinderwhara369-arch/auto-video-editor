from __future__ import annotations

import argparse
from pathlib import Path

from app.engine.beat.beat_detector import detect_beats
from app.engine.core.io import write_json, write_json_model
from app.engine.core.models import (
    Effect,
    GlobalStyle,
    Resolution,
    TemplateRecipe,
    TemplateSegment,
    Transition,
)
from app.engine.scanner.audio_utils import extract_audio, make_scan_proxy
from app.engine.scanner.flash_scanner import detect_flash_events
from app.engine.scanner.frame_sampler import FrameStat, scan_frame_stats
from app.engine.scanner.motion_scanner import average_motion_between, detect_motion_events
from app.engine.scanner.probe import probe_video
from app.engine.scanner.scene_cut_detector import detect_scene_cuts
from app.engine.scanner.style_scanner import summarize_style


def build_template_from_reference(
    reference_video: Path,
    *,
    output_template: Path,
    report_path: Path | None = None,
    template_id: str | None = None,
    name: str | None = None,
    target_duration: float | None = None,
    cut_threshold: float = 0.48,
    min_cut_gap: float = 0.18,
    beat_tolerance: float = 0.12,
    debug: bool = False,
) -> TemplateRecipe:
    probe = probe_video(reference_video)
    duration = target_duration or float(probe["duration"])
    scan_video = reference_video
    scan_proxy_path = (report_path or output_template).parent / f"{_slug(reference_video.stem)}_scan_proxy.mp4"
    stats = scan_frame_stats(scan_video)
    if len(stats) < max(5, int(float(probe["duration"]) * 5)):
        scan_video = make_scan_proxy(reference_video, scan_proxy_path, debug=debug)
        stats = scan_frame_stats(scan_video)
    style = summarize_style(stats)
    cuts = detect_scene_cuts(stats, threshold=cut_threshold, min_gap_seconds=min_cut_gap)
    flashes = detect_flash_events(stats)
    motion_events = detect_motion_events(stats)

    beat_map_payload = None
    beat_times: list[float] = []
    strong_beats: list[float] = []
    audio_extract_path = None
    if probe["has_audio"]:
        audio_extract_path = (report_path or output_template).parent / f"{reference_video.stem}_reference_audio.wav"
        try:
            extract_audio(reference_video, audio_extract_path, debug=debug)
            beat_map = detect_beats(audio_extract_path)
            beat_times = [beat for beat in beat_map.beats if 0 < beat < duration]
            strong_beats = [beat for beat in beat_map.strong_beats if 0 < beat < duration]
            beat_map_payload = beat_map.model_dump(mode="json")
        except Exception as exc:  # Scanner should still produce a template without audio.
            beat_map_payload = {"error": str(exc)}

    boundaries = _build_boundaries(
        duration=duration,
        cut_times=[cut["time"] for cut in cuts],
        beat_times=beat_times,
        min_gap=min_cut_gap,
        beat_tolerance=beat_tolerance,
    )
    segments = _build_segments(
        boundaries,
        stats,
        flashes,
        strong_beats,
        duration=duration,
    )

    recipe = TemplateRecipe(
        template_id=template_id or _slug(reference_video.stem),
        name=name or reference_video.stem.replace("_", " ").replace("-", " ").title(),
        version="1.0",
        aspect_ratio="9:16",
        resolution=Resolution(width=1080, height=1920),
        fps=30,
        total_duration=round(duration, 4),
        music_mode="user_song",
        beat_sync=True,
        beat_sync_tolerance=beat_tolerance,
        segments=segments,
        global_style=GlobalStyle(
            color_grade=style["color_grade"],
            film_grain=bool(style["film_grain"]),
            sharpen=bool(style["sharpen"]),
        ),
        scanner_metadata={
            "source_video": str(reference_video),
            "source_duration": probe["duration"],
            "source_width": probe["width"],
            "source_height": probe["height"],
            "source_fps": probe["fps"],
            "unsupported_visual_features_recorded": [
                "photo_wall_or_collage",
                "duplicate_subject",
                "masked_overlays",
                "glow_trails",
                "text_or_watermark_recreation",
            ],
        },
    )
    write_json_model(output_template, recipe)

    if report_path:
        report = {
            "source": str(reference_video),
            "scan_video_used": str(scan_video),
            "frame_stats_count": len(stats),
            "probe": probe,
            "settings": {
                "cut_threshold": cut_threshold,
                "min_cut_gap": min_cut_gap,
                "beat_tolerance": beat_tolerance,
                "target_duration": target_duration,
            },
            "style": style,
            "cuts": cuts,
            "flashes": flashes,
            "motion_events": motion_events,
            "beat_map": beat_map_payload,
            "extracted_audio": str(audio_extract_path) if audio_extract_path else None,
            "boundaries": boundaries,
            "template": recipe.model_dump(mode="json"),
        }
        write_json(report_path, report)

    return recipe


def _build_boundaries(
    *,
    duration: float,
    cut_times: list[float],
    beat_times: list[float],
    min_gap: float,
    beat_tolerance: float,
) -> list[float]:
    boundaries = [0.0]
    for cut_time in sorted(cut_times):
        if cut_time <= 0 or cut_time >= duration:
            continue
        aligned = _nearest_within(cut_time, beat_times, beat_tolerance)
        candidate = aligned if aligned is not None else cut_time
        if candidate - boundaries[-1] >= min_gap:
            boundaries.append(round(candidate, 4))
    if duration - boundaries[-1] < min_gap and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(round(duration, 4))
    return boundaries


def _nearest_within(value: float, candidates: list[float], tolerance: float) -> float | None:
    if not candidates:
        return None
    nearest = min(candidates, key=lambda candidate: abs(candidate - value))
    if abs(nearest - value) <= tolerance:
        return round(nearest, 4)
    return None


def _build_segments(
    boundaries: list[float],
    stats: list[FrameStat],
    flashes: list[dict],
    strong_beats: list[float],
    *,
    duration: float,
) -> list[TemplateSegment]:
    segments: list[TemplateSegment] = []
    last_index = len(boundaries) - 2
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        segment_duration = round(end - start, 4)
        if segment_duration <= 0:
            continue

        motion = average_motion_between(stats, start, end)
        segment_stats = _stats_between(stats, start, end)
        flash = _event_between(flashes, start, end)
        has_strong_beat = any(start <= beat <= end for beat in strong_beats)
        slot_type, required_type = _slot_for_segment(index, last_index, motion, segment_duration)
        effect = _effect_for_segment(motion, segment_duration, has_strong_beat, index, last_index, segment_stats)
        transition = _transition_for_segment(flash, motion, segment_duration, index)
        confidence = _confidence_for_segment(motion, flash, has_strong_beat)

        segments.append(
            TemplateSegment(
                index=len(segments),
                start=round(start, 4),
                end=round(end, 4),
                duration=segment_duration,
                slot_type=slot_type,
                required_clip_type=required_type,
                effect=effect,
                transition_out=transition,
                source_start=round(start, 4),
                source_end=round(end, 4),
                scanner_confidence=confidence,
                scanner_notes=_notes_for_segment(motion, flash, has_strong_beat),
            )
        )
    return segments


def _event_between(events: list[dict], start: float, end: float) -> dict | None:
    for event in events:
        if start <= event["time"] <= end:
            return event
    return None


def _stats_between(stats: list[FrameStat], start: float, end: float) -> list[FrameStat]:
    return [stat for stat in stats if start <= stat.time <= end]


def _slot_for_segment(index: int, last_index: int, motion: float, duration: float) -> tuple[str, str]:
    if index == 0:
        return "intro", "process"
    if index >= max(0, last_index - 1):
        return "ending", "final_reveal"
    if index == last_index:
        return "ending", "final_reveal"
    if index >= max(0, last_index - 3):
        return "reveal", "final_reveal"
    if motion >= 0.55 or duration <= 0.45:
        return "high_energy", "motion"
    if index % 4 == 0:
        return "detail", "detail"
    if index % 5 == 0:
        return "transition", "motion"
    return "process", "process"


def _effect_for_segment(
    motion: float,
    duration: float,
    has_strong_beat: bool,
    index: int,
    last_index: int,
    segment_stats: list[FrameStat],
) -> Effect:
    brightness_values = [stat.brightness for stat in segment_stats]
    saturation_values = [stat.saturation for stat in segment_stats]
    brightness_range = max(brightness_values) - min(brightness_values) if brightness_values else 0.0
    saturation = sum(saturation_values) / len(saturation_values) if saturation_values else 0.0
    reveal_start = max(0, last_index - 2) if last_index >= 4 else last_index
    if index >= reveal_start:
        return Effect(type="vignette_focus", intensity=0.55, metadata={"reason": "ending/reveal emphasis"})
    if has_strong_beat:
        effect_type = ["impact_zoom", "whip_pan", "rgb_glitch", "strobe"][index % 4]
        return Effect(type=effect_type, intensity=0.72, metadata={"reason": "strong beat"})
    if motion >= 0.55 or duration <= 0.45:
        effect_type = ["rgb_glitch", "motion_blur", "rotate_shake", "pixel_punch", "whip_pan"][index % 5]
        return Effect(type=effect_type, intensity=min(1.0, max(0.45, motion)), metadata={"reason": "high motion"})
    if brightness_range >= 0.32:
        return Effect(type="vhs_noise", intensity=0.5, metadata={"reason": "brightness pulse"})
    if saturation >= 0.45 and duration <= 0.8:
        return Effect(type="blur_zoom", intensity=0.55, metadata={"reason": "saturated short segment"})
    if duration >= 0.8:
        return Effect(type="slow_zoom", zoom_start=1.0, zoom_end=1.06, metadata={"reason": "longer segment"})
    return Effect(type="none", metadata={"reason": "short clean cut"})


def _transition_for_segment(flash: dict | None, motion: float, duration: float, index: int) -> Transition:
    if flash:
        flash_type = "flash_hit" if flash["type"] == "white_flash" and duration <= 0.5 else flash["type"]
        return Transition(
            type=flash_type,
            duration=min(0.09, float(flash.get("duration", 0.12))),
            metadata={"scanner_time": flash["time"], "intensity": flash.get("intensity")},
        )
    if motion >= 0.65 and duration >= 0.28:
        transition_type = ["glitch", "invert_hit", "red_hit", "strobe_hit", "blur_hit"][index % 5]
        return Transition(type=transition_type, duration=0.075, metadata={"reason": "motion burst"})
    if duration >= 0.9:
        return Transition(type="fade", duration=0.12, metadata={"reason": "long segment"})
    return Transition(type="cut")


def _confidence_for_segment(motion: float, flash: dict | None, has_strong_beat: bool) -> float:
    confidence = 0.55 + min(0.2, motion * 0.2)
    if flash:
        confidence += 0.15
    if has_strong_beat:
        confidence += 0.1
    return round(min(1.0, confidence), 4)


def _notes_for_segment(motion: float, flash: dict | None, has_strong_beat: bool) -> list[str]:
    notes = [f"motion={motion:.3f}"]
    if flash:
        notes.append(f"flash={flash['type']}@{flash['time']:.3f}")
    if has_strong_beat:
        notes.append("strong_beat_aligned")
    return notes


def _slug(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "scanned_trend"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan a trend video into a reusable template JSON.")
    parser.add_argument("reference_video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--template-id", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--target-duration", type=float, default=None)
    parser.add_argument("--cut-threshold", type=float, default=0.48)
    parser.add_argument("--min-cut-gap", type=float, default=0.18)
    parser.add_argument("--beat-tolerance", type=float, default=0.12)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    recipe = build_template_from_reference(
        args.reference_video,
        output_template=args.output,
        report_path=args.report,
        template_id=args.template_id,
        name=args.name,
        target_duration=args.target_duration,
        cut_threshold=args.cut_threshold,
        min_cut_gap=args.min_cut_gap,
        beat_tolerance=args.beat_tolerance,
        debug=args.debug,
    )
    print(f"Wrote {args.output} with {len(recipe.segments)} segments")
    if args.report:
        print(f"Wrote {args.report}")


if __name__ == "__main__":
    main()
