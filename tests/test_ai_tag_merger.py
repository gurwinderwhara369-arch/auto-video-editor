import json
from pathlib import Path

from app.engine.analyzer.ai_tag_merger import merge_ai_tags
from app.engine.core.models import ClipMetadata, ClipMetadataSet


def test_merge_ai_tags_adds_clip_semantics(tmp_path: Path) -> None:
    clip = ClipMetadata(
        clip_id="clip_001",
        filename="needle.mp4",
        path=Path("needle.mp4"),
        duration=5.0,
        width=540,
        height=960,
        fps=30,
        overall_score=0.5,
        sharpness_score=0.4,
        brightness_score=0.7,
        motion_score=0.8,
    )
    tag_dir = tmp_path / "tags"
    tag_dir.mkdir()
    (tag_dir / "needle_gemma_tags.json").write_text(
        json.dumps(
            {
                "ai_result": {
                    "overall_summary": "Needle work close-up.",
                    "clip_level_tags": ["needle_work"],
                    "frames": [
                        {
                            "primary_tag": "needle_work",
                            "confidence": 0.91,
                            "description": "Needle shading skin.",
                            "best_use": "process",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    enriched = merge_ai_tags(ClipMetadataSet(job_id="job", clips=[clip]), tag_dir)

    assert enriched.clips[0].ai_tags == ["needle_work"]
    assert enriched.clips[0].ai_confidence == 0.91
    assert enriched.clips[0].best_use == "process"
