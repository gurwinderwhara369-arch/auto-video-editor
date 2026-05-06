from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from app.engine.core.io import load_json_model, write_json_model
from app.engine.core.models import Effect, GlobalStyle, TemplateRecipe, TemplateSegment, Transition
from app.cli.render_reel import run_pipeline
from app.engine.qa.video_quality_scorer import score_video

VARIANT_NAMES = ("clean", "balanced", "aggressive")
HEAVY_EFFECTS = {
    "rgb_glitch",
    "motion_blur",
    "speed_ramp",
    "whip_pan",
    "rotate_shake",
    "strobe",
    "vhs_noise",
    "pixel_punch",
    "split_panel",
    "beat_flash_stack",
    "cutout_pop",
    "duplicate_subject_echo",
    "zoom_burst",
    "background_pulse",
    "text_flash",
    "edge_glow",
    "film_damage",
}
HIT_TRANSITIONS = {
    "flash_hit",
    "white_hit",
    "black_hit",
    "red_hit",
    "invert_hit",
    "blur_hit",
    "strobe_hit",
    "white_slam",
    "black_slam",
    "red_slam",
    "glitch_slam",
    "blur_push",
    "panel_snap",
    "freeze_cut",
    "beat_stutter",
    "glitch",
}


def build_variant_template(template: TemplateRecipe, variant: str) -> TemplateRecipe:
    if variant not in VARIANT_NAMES:
        raise ValueError(f"Unknown variant: {variant}")
    segments = [_variant_segment(segment, variant) for segment in template.segments]

    if variant == "clean":
        style = GlobalStyle(color_grade="cinematic_grade", film_grain=False, sharpen=True)
    elif variant == "aggressive":
        style = GlobalStyle(color_grade="cinematic_grade", film_grain=True, sharpen=True)
    else:
        style = template.global_style.model_copy(
            update={"color_grade": template.global_style.color_grade or "cinematic_grade", "sharpen": True}
        )

    return template.model_copy(
        update={
            "template_id": f"{template.template_id}_{variant}",
            "name": f"{template.name} {variant.title()}",
            "segments": segments,
            "global_style": style,
            "scanner_metadata": {**template.scanner_metadata, "variant": variant},
        }
    )


def _variant_segment(segment: TemplateSegment, variant: str) -> TemplateSegment:
    effect = _variant_effect(segment.effect, variant, segment.index)
    transition = _variant_transition(segment.transition_out, variant, segment.index)
    return segment.model_copy(update={"effect": effect, "transition_out": transition})


def _variant_effect(effect: Effect, variant: str, index: int) -> Effect:
    intensity = effect.intensity if effect.intensity is not None else 0.6
    metadata = {**effect.metadata, "variant_source_effect": effect.type}
    if variant == "clean":
        if effect.type in HEAVY_EFFECTS:
            return Effect(type="slow_zoom", intensity=0.25, zoom_end=1.035, metadata=metadata)
        return effect.model_copy(update={"intensity": min(intensity, 0.35), "metadata": metadata})
    if variant == "aggressive":
        aggressive_cycle = ["rgb_glitch", "whip_pan", "impact_zoom", "strobe", "rotate_shake", "pixel_punch"]
        effect_type = effect.type if effect.type != "none" else aggressive_cycle[index % len(aggressive_cycle)]
        if effect_type == "slow_zoom" and index % 3 == 0:
            effect_type = "impact_zoom"
        return Effect(type=effect_type, intensity=min(1.0, intensity * 1.35), zoom_end=effect.zoom_end, metadata=metadata)
    return effect.model_copy(update={"intensity": min(0.85, max(0.45, intensity)), "metadata": metadata})


def _variant_transition(transition: Transition, variant: str, index: int) -> Transition:
    metadata = {**transition.metadata, "variant_source_transition": transition.type}
    if variant == "clean":
        if transition.type in HIT_TRANSITIONS:
            return Transition(type="cut", metadata=metadata)
        if transition.type == "fade":
            return Transition(type="fade", duration=min(transition.duration or 0.1, 0.1), metadata=metadata)
        return transition.model_copy(update={"metadata": metadata})
    if variant == "aggressive":
        if transition.type == "cut":
            transition_type = ["white_hit", "black_hit", "red_hit", "invert_hit"][index % 4]
            return Transition(type=transition_type, duration=0.055, metadata=metadata)
        return transition.model_copy(update={"duration": min(transition.duration or 0.06, 0.08), "metadata": metadata})
    if transition.type in HIT_TRANSITIONS:
        return transition.model_copy(update={"duration": min(transition.duration or 0.055, 0.065), "metadata": metadata})
    return transition.model_copy(update={"metadata": metadata})


def render_variants(
    *,
    template_path: Path,
    clips_dir: Path,
    song_path: Path,
    output_dir: Path,
    selected_output: Path,
    metadata_path: Path | None = None,
    moments_path: Path | None = None,
    beat_map_path: Path | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = load_json_model(template_path, TemplateRecipe)
    reports: list[dict[str, Any]] = []

    for variant in VARIANT_NAMES:
        variant_template = build_variant_template(template, variant)
        variant_template_path = output_dir / f"{variant}_template.json"
        variant_output = output_dir / f"{variant}.mp4"
        write_json_model(variant_template_path, variant_template)
        run_pipeline(
            template_path=variant_template_path,
            clips_dir=clips_dir,
            song_path=song_path,
            output_path=variant_output,
            metadata_path=metadata_path,
            moments_path=moments_path,
            beat_map_path=beat_map_path,
            temp_dir=output_dir / f"_{variant}_segments",
            debug=debug,
        )
        qa = score_video(variant_output)
        reports.append({"variant": variant, "output": str(variant_output), "qa": qa})

    best = max(reports, key=lambda item: item["qa"]["score"])
    selected_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best["output"], selected_output)
    report = {
        "selected_variant": best["variant"],
        "selected_output": str(selected_output),
        "variants": reports,
    }
    (output_dir / "qa_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Render clean/balanced/aggressive variants and select the best by QA score.")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--song", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selected-output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--moments", type=Path, default=None)
    parser.add_argument("--beat-map", type=Path, default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    report = render_variants(
        template_path=args.template,
        clips_dir=args.clips,
        song_path=args.song,
        output_dir=args.output_dir,
        selected_output=args.selected_output,
        metadata_path=args.metadata,
        moments_path=args.moments,
        beat_map_path=args.beat_map,
        debug=args.debug,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
