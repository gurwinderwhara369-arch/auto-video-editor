from pathlib import Path

from app.engine.core.io import load_json_model
from app.engine.core.models import ClipMetadata, ClipMetadataSet, CropMetadata, MomentMetadata, MomentMetadataSet, TemplateRecipe
from app.engine.planner.edit_planner import build_timeline


def test_planner_creates_template_sized_timeline() -> None:
    template = load_json_model(Path("templates/fast_glitch.json"), TemplateRecipe)
    metadata = ClipMetadataSet(
        job_id="job_test",
        clips=[
            ClipMetadata(
                clip_id="clip_001",
                filename="a.mp4",
                path=Path("a.mp4"),
                duration=20.0,
                width=1920,
                height=1080,
                fps=30,
                overall_score=0.9,
                sharpness_score=0.9,
                brightness_score=0.8,
                motion_score=0.7,
            ),
            ClipMetadata(
                clip_id="clip_002",
                filename="b.mp4",
                path=Path("b.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.7,
                sharpness_score=0.8,
                brightness_score=0.8,
                motion_score=0.9,
            ),
        ],
    )

    timeline = build_timeline(
        template,
        metadata,
        Path("song.mp3"),
        Path("out.mp4"),
    )

    assert len(timeline.timeline) == len(template.segments)
    assert timeline.timeline[-1].timeline_end == 15.0
    assert timeline.resolution.width == 1080
    assert timeline.resolution.height == 1920


def test_planner_prefers_ai_reveal_for_reveal_slot() -> None:
    template = load_json_model(Path("templates/fast_glitch.json"), TemplateRecipe)
    reveal_segment = template.segments[-1].model_copy(
        update={"slot_type": "ending", "required_clip_type": "final_reveal"}
    )
    template = template.model_copy(update={"segments": [reveal_segment], "total_duration": reveal_segment.duration})
    metadata = ClipMetadataSet(
        job_id="job_test",
        clips=[
            ClipMetadata(
                clip_id="clip_motion",
                filename="motion.mp4",
                path=Path("motion.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.9,
                sharpness_score=0.9,
                brightness_score=0.8,
                motion_score=1.0,
                ai_tags=["needle_work"],
                ai_confidence=0.8,
                best_use="process",
            ),
            ClipMetadata(
                clip_id="clip_reveal",
                filename="reveal.mp4",
                path=Path("reveal.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.55,
                sharpness_score=0.55,
                brightness_score=0.7,
                motion_score=0.2,
                ai_tags=["final_reveal"],
                ai_confidence=0.95,
                best_use="ending",
            ),
        ],
    )

    timeline = build_timeline(template, metadata, Path("song.mp3"), Path("out.mp4"))

    assert timeline.timeline[0].clip_id == "clip_reveal"


def test_planner_avoids_immediate_clip_repetition_when_possible() -> None:
    template = load_json_model(Path("templates/fast_glitch.json"), TemplateRecipe)
    first_two = template.model_copy(
        update={"segments": template.segments[:2], "total_duration": sum(segment.duration for segment in template.segments[:2])}
    )
    metadata = ClipMetadataSet(
        job_id="job_test",
        clips=[
            ClipMetadata(
                clip_id="clip_best",
                filename="best.mp4",
                path=Path("best.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.9,
                sharpness_score=0.9,
                brightness_score=0.8,
                motion_score=0.9,
                ai_tags=["needle_work"],
                ai_confidence=0.9,
                best_use="process",
            ),
            ClipMetadata(
                clip_id="clip_alt",
                filename="alt.mp4",
                path=Path("alt.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.82,
                sharpness_score=0.82,
                brightness_score=0.8,
                motion_score=0.85,
                ai_tags=["needle_work"],
                ai_confidence=0.9,
                best_use="process",
            ),
        ],
    )

    timeline = build_timeline(first_two, metadata, Path("song.mp3"), Path("out.mp4"))

    assert timeline.timeline[0].clip_id != timeline.timeline[1].clip_id


def test_planner_uses_moment_metadata_when_provided() -> None:
    template = load_json_model(Path("templates/fast_glitch.json"), TemplateRecipe)
    one_segment = template.model_copy(update={"segments": [template.segments[0]], "total_duration": template.segments[0].duration})
    metadata = ClipMetadataSet(
        job_id="job_test",
        clips=[
            ClipMetadata(
                clip_id="clip_001",
                filename="a.mp4",
                path=Path("a.mp4"),
                duration=20.0,
                width=1080,
                height=1920,
                fps=30,
                overall_score=0.7,
                sharpness_score=0.7,
                brightness_score=0.8,
                motion_score=0.6,
                ai_tags=["needle_work"],
            )
        ],
    )
    moments = MomentMetadataSet(
        job_id="job_test",
        moments=[
            MomentMetadata(
                moment_id="moment_best",
                clip_id="clip_001",
                source_file=Path("a.mp4"),
                start=4.0,
                end=5.2,
                duration=1.2,
                moment_type="needle_work",
                score=0.95,
                sharpness_score=0.9,
                brightness_score=0.8,
                motion_score=0.8,
                stability_score=0.7,
                crop=CropMetadata(crop_x=0.4, crop_y=0.6, crop_zoom=1.1, framing_confidence=0.8),
            )
        ],
    )

    timeline = build_timeline(one_segment, metadata, Path("song.mp3"), Path("out.mp4"), moments=moments)

    assert timeline.timeline[0].moment_id == "moment_best"
    assert timeline.timeline[0].source_start == 4.0
    assert timeline.timeline[0].crop is not None
