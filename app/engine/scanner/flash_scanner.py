from __future__ import annotations

from app.engine.scanner.frame_sampler import FrameStat


def detect_flash_events(
    stats: list[FrameStat],
    *,
    min_gap_seconds: float = 0.12,
) -> list[dict]:
    events: list[dict] = []
    if len(stats) < 3:
        return events

    last_event = -999.0
    for previous, current in zip(stats, stats[1:], strict=False):
        if current.time - last_event < min_gap_seconds:
            continue
        delta = current.brightness - previous.brightness
        if delta >= 0.28 or current.brightness >= 0.86:
            events.append(
                {
                    "time": current.time,
                    "type": "white_flash",
                    "duration": 0.12,
                    "intensity": round(min(1.0, abs(delta) * 2.2), 4),
                }
            )
            last_event = current.time
        elif delta <= -0.28 or current.brightness <= 0.08:
            events.append(
                {
                    "time": current.time,
                    "type": "black_flash",
                    "duration": 0.12,
                    "intensity": round(min(1.0, abs(delta) * 2.2), 4),
                }
            )
            last_event = current.time
    return events
