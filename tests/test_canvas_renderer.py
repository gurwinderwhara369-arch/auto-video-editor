from pathlib import Path

import cv2
import numpy as np

from app.engine.core.models import (
    Resolution,
    Timeline,
    TimelineAudio,
    TimelineSegment,
    VisualEvent,
)
from app.engine.renderer.canvas_renderer import CANVAS_EFFECTS, _apply_visual_events, _canvas_effect_for_segment, _compose_base


def test_canvas_base_composition_targets_reels_resolution() -> None:
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)

    composed = _compose_base(frame, Resolution(width=1080, height=1920))

    assert composed.shape == (1920, 1080, 3)


def test_canvas_effect_assignment_cycles_for_segments(tmp_path: Path) -> None:
    segment = TimelineSegment(
        segment_index=3,
        clip_id="clip_001",
        source_file=tmp_path / "clip.mp4",
        source_start=0,
        source_end=1,
        timeline_start=0,
        timeline_end=1,
    )

    assert _canvas_effect_for_segment(segment) == "split_panel"


def test_canvas_video_writer_available(tmp_path: Path) -> None:
    output = tmp_path / "test.mp4"
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 30, (108, 192))
    assert writer.isOpened()
    writer.write(np.zeros((192, 108, 3), dtype=np.uint8))
    writer.release()
    assert output.exists()


def test_canvas_effect_assignment_uses_visual_events(tmp_path: Path) -> None:
    segment = TimelineSegment(
        segment_index=0,
        clip_id="clip_001",
        source_file=tmp_path / "clip.mp4",
        source_start=0,
        source_end=1,
        timeline_start=0,
        timeline_end=1,
        visual_events=[VisualEvent(type="panel_split", start=0, end=0.2)],
    )

    assert _canvas_effect_for_segment(segment) == "split_panel"


def test_canvas_visual_event_overlay_preserves_resolution(tmp_path: Path) -> None:
    segment = TimelineSegment(
        segment_index=0,
        clip_id="clip_001",
        source_file=tmp_path / "clip.mp4",
        source_start=0,
        source_end=1,
        timeline_start=0,
        timeline_end=1,
        visual_events=[VisualEvent(type="flash_stack", start=0, end=0.5, intensity=0.8)],
    )
    frame = np.full((192, 108, 3), 90, dtype=np.uint8)

    output = _apply_visual_events(frame, segment, 0.1)

    assert output.shape == frame.shape
    assert len(CANVAS_EFFECTS) >= 10
