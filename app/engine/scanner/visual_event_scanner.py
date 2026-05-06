from __future__ import annotations

from app.engine.core.models import VisualEvent
from app.engine.scanner.frame_sampler import FrameStat


SUPPORTED_VISUAL_EVENTS = {
    "freeze",
    "panel_split",
    "blur_wall",
    "cutout_overlay",
    "echo_trail",
    "text_zone",
    "flash_stack",
    "zoom_burst",
    "shake_hit",
    "background_pulse",
}


def detect_visual_events(
    stats: list[FrameStat],
    *,
    flashes: list[dict] | None = None,
    motion_events: list[dict] | None = None,
) -> list[dict]:
    events: list[dict] = []
    events.extend(_freeze_events(stats))
    events.extend(_brightness_pulse_events(stats))
    events.extend(_zoom_or_shake_events(stats))
    events.extend(_text_zone_events(stats))
    events.extend(_panel_split_events(stats))

    for flash in flashes or []:
        events.append(
            {
                "type": "flash_stack",
                "start": round(max(0.0, float(flash["time"]) - 0.03), 4),
                "end": round(float(flash["time"]) + float(flash.get("duration", 0.1)), 4),
                "intensity": float(flash.get("intensity", 0.75)),
                "confidence": 0.78,
                "metadata": {"source": "flash_detector", "flash_type": flash.get("type")},
            }
        )

    for event in motion_events or []:
        if float(event.get("score", 0.0)) >= 0.72:
            events.append(
                {
                    "type": "echo_trail",
                    "start": float(event["start"]),
                    "end": float(event["end"]),
                    "intensity": min(1.0, float(event.get("score", 0.72))),
                    "confidence": 0.68,
                    "metadata": {"source": "motion_detector"},
                }
            )

    return _merge_close_events(sorted(events, key=lambda item: (item["start"], item["type"])))


def events_for_segment(events: list[dict], start: float, end: float) -> list[VisualEvent]:
    segment_events: list[VisualEvent] = []
    for event in events:
        event_start = float(event["start"])
        event_end = float(event.get("end") or event_start)
        if event_end < start or event_start > end:
            continue
        local_start = max(0.0, event_start - start)
        local_end = max(local_start, min(end, event_end) - start)
        segment_events.append(
            VisualEvent(
                type=str(event["type"]),
                start=round(local_start, 4),
                end=round(local_end, 4),
                intensity=float(event.get("intensity", 0.6)),
                confidence=float(event.get("confidence", 0.6)),
                metadata=dict(event.get("metadata", {})),
            )
        )
    return segment_events


def summarize_visual_events(events: list[dict]) -> dict[str, int]:
    summary = {event_type: 0 for event_type in sorted(SUPPORTED_VISUAL_EVENTS)}
    for event in events:
        event_type = str(event.get("type", "unknown"))
        summary[event_type] = summary.get(event_type, 0) + 1
    return summary


def _freeze_events(stats: list[FrameStat]) -> list[dict]:
    events: list[dict] = []
    start: float | None = None
    scores: list[float] = []
    for stat in stats:
        is_freeze_like = stat.frame_diff <= 0.012 and stat.hist_diff <= 0.045 and stat.sharpness >= 0.18
        if is_freeze_like:
            if start is None:
                start = stat.time
            scores.append(1.0 - min(1.0, stat.frame_diff / 0.012))
        elif start is not None:
            if stat.time - start >= 0.16:
                events.append(
                    {
                        "type": "freeze",
                        "start": round(start, 4),
                        "end": round(stat.time, 4),
                        "intensity": round(sum(scores) / len(scores), 4),
                        "confidence": 0.7,
                        "metadata": {"source": "frame_repeat_detector"},
                    }
                )
            start = None
            scores = []
    if start is not None and stats and stats[-1].time - start >= 0.16:
        events.append(
            {
                "type": "freeze",
                "start": round(start, 4),
                "end": round(stats[-1].time, 4),
                "intensity": round(sum(scores) / len(scores), 4),
                "confidence": 0.7,
                "metadata": {"source": "frame_repeat_detector"},
            }
        )
    return events


def _brightness_pulse_events(stats: list[FrameStat]) -> list[dict]:
    events: list[dict] = []
    for previous, current in zip(stats, stats[1:], strict=False):
        delta = abs(current.brightness - previous.brightness)
        if delta >= 0.22:
            events.append(
                {
                    "type": "background_pulse",
                    "start": current.time,
                    "end": round(current.time + 0.18, 4),
                    "intensity": min(1.0, delta * 2.4),
                    "confidence": 0.62,
                    "metadata": {"source": "brightness_delta"},
                }
            )
    return events


def _zoom_or_shake_events(stats: list[FrameStat]) -> list[dict]:
    events: list[dict] = []
    for stat in stats:
        if stat.motion >= 0.72 and stat.hist_diff <= 0.22:
            events.append(
                {
                    "type": "zoom_burst",
                    "start": stat.time,
                    "end": round(stat.time + 0.16, 4),
                    "intensity": stat.motion,
                    "confidence": 0.58,
                    "metadata": {"source": "motion_without_scene_change"},
                }
            )
        elif stat.frame_diff >= 0.16 and stat.hist_diff >= 0.18:
            events.append(
                {
                    "type": "shake_hit",
                    "start": stat.time,
                    "end": round(stat.time + 0.12, 4),
                    "intensity": min(1.0, stat.frame_diff / 0.24),
                    "confidence": 0.55,
                    "metadata": {"source": "frame_diff_spike"},
                }
            )
    return events


def _text_zone_events(stats: list[FrameStat]) -> list[dict]:
    events: list[dict] = []
    for stat in stats:
        if stat.sharpness >= 0.72 and stat.contrast >= 0.45 and stat.motion <= 0.18:
            events.append(
                {
                    "type": "text_zone",
                    "start": stat.time,
                    "end": round(stat.time + 0.24, 4),
                    "intensity": min(1.0, stat.sharpness),
                    "confidence": 0.5,
                    "metadata": {"source": "sharp_static_high_contrast"},
                }
            )
    return events


def _panel_split_events(stats: list[FrameStat]) -> list[dict]:
    events: list[dict] = []
    for stat in stats:
        if stat.contrast >= 0.62 and stat.saturation >= 0.38 and stat.hist_diff >= 0.34:
            events.append(
                {
                    "type": "panel_split",
                    "start": stat.time,
                    "end": round(stat.time + 0.3, 4),
                    "intensity": min(1.0, stat.contrast),
                    "confidence": 0.52,
                    "metadata": {"source": "layout_change_heuristic"},
                }
            )
    return events


def _merge_close_events(events: list[dict], *, min_gap: float = 0.08) -> list[dict]:
    merged: list[dict] = []
    for event in events:
        if (
            merged
            and event["type"] == merged[-1]["type"]
            and float(event["start"]) - float(merged[-1].get("end", merged[-1]["start"])) <= min_gap
        ):
            merged[-1]["end"] = max(float(merged[-1].get("end", merged[-1]["start"])), float(event.get("end", event["start"])))
            merged[-1]["intensity"] = max(float(merged[-1].get("intensity", 0.0)), float(event.get("intensity", 0.0)))
            merged[-1]["confidence"] = max(float(merged[-1].get("confidence", 0.0)), float(event.get("confidence", 0.0)))
        else:
            merged.append(dict(event))
    return merged
