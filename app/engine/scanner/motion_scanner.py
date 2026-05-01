from __future__ import annotations

from app.engine.scanner.frame_sampler import FrameStat


def detect_motion_events(
    stats: list[FrameStat],
    *,
    threshold: float = 0.45,
    min_duration: float = 0.12,
) -> list[dict]:
    events: list[dict] = []
    start: float | None = None
    scores: list[float] = []

    for stat in stats:
        if stat.motion >= threshold:
            if start is None:
                start = stat.time
            scores.append(stat.motion)
        elif start is not None:
            end = stat.time
            if end - start >= min_duration:
                events.append(
                    {
                        "start": round(start, 4),
                        "end": round(end, 4),
                        "type": "high_motion",
                        "score": round(sum(scores) / len(scores), 4),
                    }
                )
            start = None
            scores = []

    if start is not None and stats:
        end = stats[-1].time
        if end - start >= min_duration:
            events.append(
                {
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "type": "high_motion",
                    "score": round(sum(scores) / len(scores), 4),
                }
            )
    return events


def average_motion_between(stats: list[FrameStat], start: float, end: float) -> float:
    selected = [stat.motion for stat in stats if start <= stat.time < end]
    if not selected:
        return 0.0
    return sum(selected) / len(selected)
