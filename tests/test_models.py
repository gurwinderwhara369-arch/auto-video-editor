from pathlib import Path

import pytest

from app.engine.core.io import load_json_model
from app.engine.core.models import TemplateRecipe, TimelineSegment


def test_fast_glitch_template_loads() -> None:
    template = load_json_model(Path("templates/fast_glitch.json"), TemplateRecipe)

    assert template.template_id == "fast_glitch_reveal_001"
    assert template.resolution.width == 1080
    assert template.resolution.height == 1920
    assert sum(segment.duration for segment in template.segments) == pytest.approx(15.0)


def test_timeline_segment_rejects_bad_timing() -> None:
    with pytest.raises(ValueError):
        TimelineSegment(
            segment_index=0,
            clip_id="clip_001",
            source_file=Path("clip.mp4"),
            source_start=2.0,
            source_end=1.0,
            timeline_start=0.0,
            timeline_end=1.0,
        )
