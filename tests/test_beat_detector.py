from app.engine.core.models import BeatMap, EnergyPeak
from app.engine.beat.beat_detector import select_audio_window_start


def test_select_audio_window_uses_strongest_energy_peak_with_lead_in() -> None:
    beat_map = BeatMap(
        audio_file="song.mp3",
        duration=30.0,
        bpm=140.0,
        beats=[1.0, 2.0, 3.0],
        strong_beats=[10.0],
        energy_peaks=[
            EnergyPeak(time=4.0, strength=0.4, type="drop_candidate"),
            EnergyPeak(time=12.0, strength=1.0, type="drop_candidate"),
        ],
    )

    assert select_audio_window_start(beat_map, 10.0) == 10.8


def test_select_audio_window_stays_at_zero_for_short_audio() -> None:
    beat_map = BeatMap(audio_file="song.mp3", duration=8.0, bpm=120.0)

    assert select_audio_window_start(beat_map, 10.0) == 0.0
