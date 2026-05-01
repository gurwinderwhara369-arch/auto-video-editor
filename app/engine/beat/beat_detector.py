from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np

from app.engine.core.io import write_json_model
from app.engine.core.models import BeatMap, EnergyPeak


def select_audio_window_start(beat_map: BeatMap | None, target_duration: float) -> float:
    if not beat_map or target_duration <= 0 or beat_map.duration <= target_duration:
        return 0.0

    candidates = sorted(
        beat_map.energy_peaks,
        key=lambda peak: peak.strength,
        reverse=True,
    )
    anchor = candidates[0].time if candidates else None
    if anchor is None and beat_map.strong_beats:
        anchor = beat_map.strong_beats[min(len(beat_map.strong_beats) // 2, len(beat_map.strong_beats) - 1)]
    if anchor is None:
        return 0.0

    # Start just before the strongest energy area so the first visual hit has a musical lead-in.
    start = anchor - min(1.2, target_duration * 0.25)
    max_start = max(0.0, beat_map.duration - target_duration)
    return round(max(0.0, min(start, max_start)), 3)


def detect_beats(audio_path: Path) -> BeatMap:
    cache_dir = Path("workspace/.cache/numba").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_dir))
    import librosa

    y, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sample_rate))
    onset_env = librosa.onset.onset_strength(y=y, sr=sample_rate)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sample_rate, onset_envelope=onset_env)
    beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)

    strengths = onset_env[beat_frames] if len(beat_frames) else np.array([])
    strong_beats: list[float] = []
    if strengths.size:
        threshold = float(np.quantile(strengths, 0.75))
        strong_beats = [
            float(time)
            for time, strength in zip(beat_times, strengths, strict=False)
            if float(strength) >= threshold
        ]

    rms = librosa.feature.rms(y=y)[0]
    peak_indexes = np.argpartition(rms, -min(3, len(rms)))[-min(3, len(rms)) :] if len(rms) else []
    max_rms = float(rms.max()) if len(rms) and float(rms.max()) > 0 else 1.0
    energy_peaks = [
        EnergyPeak(
            time=float(librosa.frames_to_time(index, sr=sample_rate)),
            strength=max(0.0, min(1.0, float(rms[index]) / max_rms)),
            type="drop_candidate",
        )
        for index in sorted(peak_indexes)
    ]

    bpm = float(tempo[0] if isinstance(tempo, np.ndarray) else tempo)
    return BeatMap(
        audio_file=str(audio_path),
        duration=duration,
        bpm=bpm,
        beats=[float(time) for time in beat_times],
        strong_beats=strong_beats,
        energy_peaks=energy_peaks,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect beat map for a song.")
    parser.add_argument("song", type=Path)
    parser.add_argument("--output", type=Path, default=Path("beat_map.json"))
    args = parser.parse_args()

    beat_map = detect_beats(args.song)
    write_json_model(args.output, beat_map)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
