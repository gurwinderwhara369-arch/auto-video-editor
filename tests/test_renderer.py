from app.engine.core.models import CropMetadata, Effect, GlobalStyle, Resolution
from app.engine.renderer.effects import build_effect_filters, build_vertical_crop_filter


def test_vertical_crop_filter_targets_reels_resolution() -> None:
    filter_graph = build_vertical_crop_filter(Resolution(width=1080, height=1920))

    assert "scale=" in filter_graph
    assert "crop=1080:1920" in filter_graph


def test_scanner_generated_glitch_effect_is_renderable_filter() -> None:
    filters = build_effect_filters(
        Effect(type="glitch", intensity=0.7),
        GlobalStyle(color_grade="high_contrast_dark", film_grain=True, sharpen=True),
        Resolution(width=1080, height=1920),
    )

    filter_graph = ",".join(filters)
    assert "crop=iw-" in filter_graph
    assert "eq=" in filter_graph
    assert "noise=" in filter_graph


def test_pro_effect_types_are_renderable_filters() -> None:
    resolution = Resolution(width=1080, height=1920)
    style = GlobalStyle(color_grade="cinematic_grade", film_grain=True, sharpen=True)

    for effect_type in [
        "impact_zoom",
        "speed_ramp",
        "rgb_glitch",
        "motion_blur",
        "whip_pan",
        "rotate_shake",
        "blur_zoom",
        "strobe",
        "vhs_noise",
        "pixel_punch",
        "vignette_focus",
    ]:
        filters = build_effect_filters(
            Effect(type=effect_type, intensity=0.75, metadata={"source_duration": 0.7}),
            style,
            resolution,
            segment_duration=0.5,
            fps=30,
        )
        filter_graph = ",".join(filters)

        assert "crop=1080:1920" in filter_graph
        assert "eq=" in filter_graph


def test_vertical_crop_filter_accepts_smart_crop_metadata() -> None:
    filter_graph = build_vertical_crop_filter(
        Resolution(width=1080, height=1920),
        crop=CropMetadata(crop_x=0.35, crop_y=0.65, crop_zoom=1.12, framing_confidence=0.8),
    )

    assert "scale=" in filter_graph
    assert "crop=1080:1920:" in filter_graph
    assert "0.3500" in filter_graph
    assert "0.6500" in filter_graph
