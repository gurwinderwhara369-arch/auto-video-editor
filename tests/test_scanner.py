from pathlib import Path

from app.engine.core.models import TemplateRecipe
from app.engine.scanner.flash_scanner import detect_flash_events
from app.engine.scanner.frame_sampler import FrameStat
from app.engine.scanner.scene_cut_detector import detect_scene_cuts
from app.engine.scanner.template_builder import _build_boundaries, _build_segments


def test_scene_cut_detector_finds_histogram_jump() -> None:
    stats = [
        FrameStat(0.0, 0.2, 0.2, 0.2, 0.2, 0.0, 0.0, 0.0),
        FrameStat(0.1, 0.2, 0.2, 0.2, 0.2, 0.0, 0.2, 0.02),
        FrameStat(0.3, 0.8, 0.2, 0.2, 0.2, 0.8, 0.7, 0.3),
    ]

    cuts = detect_scene_cuts(stats, threshold=0.48, min_gap_seconds=0.18)

    assert cuts[0]["time"] == 0.3


def test_flash_detector_finds_white_and_black_flash() -> None:
    stats = [
        FrameStat(0.0, 0.3, 0.2, 0.2, 0.2, 0.0, 0.0, 0.0),
        FrameStat(0.2, 0.95, 0.2, 0.2, 0.2, 0.0, 0.0, 0.0),
        FrameStat(0.5, 0.35, 0.2, 0.2, 0.2, 0.0, 0.0, 0.0),
        FrameStat(0.8, 0.02, 0.2, 0.2, 0.2, 0.0, 0.0, 0.0),
    ]

    events = detect_flash_events(stats)

    assert events[0]["type"] == "white_flash"
    assert events[1]["type"] == "black_flash"


def test_template_segments_from_boundaries_validate() -> None:
    stats = [
        FrameStat(0.0, 0.3, 0.2, 0.2, 0.2, 0.1, 0.0, 0.0),
        FrameStat(0.4, 0.4, 0.2, 0.2, 0.2, 0.8, 0.0, 0.0),
        FrameStat(0.9, 0.4, 0.2, 0.2, 0.2, 0.2, 0.0, 0.0),
        FrameStat(1.3, 0.4, 0.2, 0.2, 0.2, 0.2, 0.0, 0.0),
    ]
    boundaries = _build_boundaries(
        duration=1.4,
        cut_times=[0.4, 0.9],
        beat_times=[0.42, 0.88],
        min_gap=0.18,
        beat_tolerance=0.12,
    )

    segments = _build_segments(boundaries, stats, [], [0.42], duration=1.4)
    template = TemplateRecipe(
        template_id="test_scan",
        name="Test Scan",
        total_duration=1.4,
        segments=segments,
    )

    assert template.segments[0].start == 0.0
    assert template.segments[-1].end == 1.4
    assert all(segment.scanner_confidence is not None for segment in template.segments)


def test_scanner_maps_fast_motion_to_expanded_effects() -> None:
    stats = [
        FrameStat(0.0, 0.3, 0.5, 0.2, 0.2, 0.1, 0.0, 0.0),
        FrameStat(0.2, 0.4, 0.5, 0.2, 0.2, 0.9, 0.8, 0.5),
        FrameStat(0.4, 0.4, 0.5, 0.2, 0.2, 0.8, 0.8, 0.5),
    ]

    segments = _build_segments([0.0, 0.4, 0.8, 1.2], stats, [], [], duration=1.2)

    assert segments[1].effect.type in {
        "rgb_glitch",
        "motion_blur",
        "rotate_shake",
        "pixel_punch",
        "whip_pan",
        "impact_zoom",
        "strobe",
    }
