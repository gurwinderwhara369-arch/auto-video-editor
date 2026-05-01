from pathlib import Path

from app.engine.core.io import load_json_model
from app.engine.core.models import TemplateRecipe
from app.cli.render_variants import build_variant_template


def test_variant_templates_have_distinct_effect_profiles() -> None:
    template = load_json_model(Path("templates/montagem_tentana_v2.json"), TemplateRecipe)

    clean = build_variant_template(template, "clean")
    aggressive = build_variant_template(template, "aggressive")

    clean_heavy = {segment.effect.type for segment in clean.segments}
    aggressive_heavy = {segment.effect.type for segment in aggressive.segments}

    assert clean.template_id.endswith("_clean")
    assert aggressive.template_id.endswith("_aggressive")
    assert "strobe" not in clean_heavy
    assert {"strobe", "whip_pan", "rgb_glitch"} & aggressive_heavy
