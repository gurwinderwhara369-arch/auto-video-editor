from __future__ import annotations

from app.engine.scanner.frame_sampler import FrameStat


def detect_scene_cuts(
    stats: list[FrameStat],
    *,
    threshold: float = 0.48,
    min_gap_seconds: float = 0.18,
) -> list[dict]:
    cuts: list[dict] = []
    last_cut = 0.0
    for stat in stats[1:]:
        score = max(stat.hist_diff, stat.frame_diff * 2.8)
        if score >= threshold and stat.time - last_cut >= min_gap_seconds:
            cuts.append(
                {
                    "time": stat.time,
                    "score": round(min(1.0, score), 4),
                    "hist_diff": round(stat.hist_diff, 4),
                    "frame_diff": round(stat.frame_diff, 4),
                }
            )
            last_cut = stat.time
    return cuts
