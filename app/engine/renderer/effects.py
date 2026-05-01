from __future__ import annotations

from app.engine.core.models import CropMetadata, Effect, GlobalStyle, Resolution


def build_vertical_crop_filter(resolution: Resolution, crop: CropMetadata | None = None) -> str:
    width = resolution.width
    height = resolution.height
    zoom = crop.crop_zoom if crop else 1.0
    crop_x = crop.crop_x if crop else 0.5
    crop_y = crop.crop_y if crop else 0.5
    scaled_width = int(width * zoom)
    scaled_height = int(height * zoom)
    return (
        f"scale='if(gt(a,{width}/{height}),-2,{scaled_width})':"
        f"'if(gt(a,{width}/{height}),{scaled_height},-2)',"
        f"crop={width}:{height}:"
        f"(iw-{width})*{crop_x:.4f}:"
        f"(ih-{height})*{crop_y:.4f}"
    )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_effect_filters(
    effect: Effect,
    style: GlobalStyle,
    resolution: Resolution,
    *,
    segment_duration: float | None = None,
    fps: int = 30,
    crop: CropMetadata | None = None,
) -> list[str]:
    filters = [build_vertical_crop_filter(resolution, crop=crop)]
    intensity = _clamp(effect.intensity if effect.intensity is not None else 0.6)

    if effect.type in {"slow_zoom", "zoom_punch"}:
        if effect.zoom_end:
            zoom = effect.zoom_end
        else:
            zoom = 1.04 + (0.14 * max(0.0, min(1.0, intensity)))
            if effect.type == "slow_zoom":
                zoom = min(zoom, 1.08)
        scaled_width = int(resolution.width * zoom)
        scaled_height = int(resolution.height * zoom)
        filters.append(
            f"scale={scaled_width}:{scaled_height},"
            f"crop={resolution.width}:{resolution.height}"
        )

    if effect.type == "impact_zoom":
        max_zoom = 1.08 + (0.18 * intensity)
        filters.append(
            "zoompan="
            f"z='min(1+({max_zoom - 1:.4f})*on/8,{max_zoom:.4f})':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={resolution.width}x{resolution.height}:fps={fps}"
        )
        filters.append("eq=contrast=1.12:saturation=1.08")

    if effect.type == "speed_ramp":
        source_duration = float(effect.metadata.get("source_duration", 0) or 0)
        output_duration = segment_duration or source_duration
        if source_duration > 0 and output_duration > 0:
            speed = max(0.65, min(0.98, output_duration / source_duration))
            filters.append(f"setpts={speed:.5f}*PTS")
        filters.append("tmix=frames=2:weights='1 1'")

    if effect.type == "motion_blur":
        filters.append("minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir")
        filters.append(f"fps={fps}")
        filters.append("tmix=frames=3:weights='1 2 1'")
        filters.append("eq=contrast=1.08:saturation=1.08")

    if effect.type == "rgb_glitch":
        shift = max(2, int(8 * intensity))
        filters.append(f"rgbashift=rh={shift}:bh=-{shift}:rv={max(1, shift // 2)}:bv=-{max(1, shift // 2)}")
        filters.append(f"chromashift=cbh={shift}:crh=-{shift}")
        filters.append("eq=contrast=1.2:saturation=1.25")

    if effect.type == "whip_pan":
        amplitude = max(18, int(58 * intensity))
        inset = amplitude * 2
        filters.append(
            f"crop=iw-{inset}:ih:"
            f"{amplitude}+{amplitude}*sin(n*1.65):0"
        )
        filters.append(f"scale={resolution.width}:{resolution.height}")
        filters.append("tmix=frames=2:weights='1 1'")

    if effect.type == "rotate_shake":
        angle = 0.006 + (0.018 * intensity)
        filters.append(f"rotate='{angle:.4f}*sin(n*0.85)':fillcolor=black")
        filters.append(f"scale={resolution.width}:{resolution.height},crop={resolution.width}:{resolution.height}")

    if effect.type == "blur_zoom":
        max_zoom = 1.05 + (0.12 * intensity)
        filters.append(
            "zoompan="
            f"z='min(1+({max_zoom - 1:.4f})*on/12,{max_zoom:.4f})':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={resolution.width}x{resolution.height}:fps={fps}"
        )
        filters.append("boxblur=2:1")
        filters.append("eq=contrast=1.08:saturation=1.08")

    if effect.type == "strobe":
        filters.append("eq=brightness='0.16*lt(mod(n,4),2)':contrast=1.18:saturation=1.15")

    if effect.type == "vhs_noise":
        filters.append("chromashift=cbh=3:crh=-3")
        filters.append("noise=alls=12:allf=t+u")
        filters.append("eq=contrast=1.1:saturation=0.92")

    if effect.type == "pixel_punch":
        filters.append("scale=iw/12:ih/12,scale=iw*12:ih*12:flags=neighbor")
        filters.append(f"scale={resolution.width}:{resolution.height}")

    if effect.type == "vignette_focus":
        filters.append("vignette=PI/5")
        filters.append("eq=contrast=1.12:saturation=1.08")

    if effect.type in {"shake", "glitch"}:
        amplitude = max(4, int(18 * max(0.1, min(1.0, intensity))))
        inset = amplitude * 2
        filters.append(
            f"crop=iw-{inset}:ih-{inset}:"
            f"{amplitude}+{amplitude}*sin(n*0.9):"
            f"{amplitude}+{amplitude}*cos(n*1.1)"
        )
        filters.append(f"scale={resolution.width}:{resolution.height}")
        if effect.type == "glitch":
            filters.append("eq=saturation=1.35:contrast=1.12")

    if style.color_grade == "cinematic_grade":
        filters.append("hqdn3d=1.5:1.5:4:4")
        filters.append("eq=contrast=1.22:brightness=-0.025:saturation=1.18")
    elif style.color_grade in {"high_contrast_dark", "dark_cinematic"}:
        filters.append("eq=contrast=1.18:brightness=-0.035:saturation=1.12")
    elif style.color_grade:
        filters.append("eq=contrast=1.08:saturation=1.05")

    if style.sharpen:
        filters.append("unsharp=5:5:0.7:3:3:0.3")

    if style.film_grain:
        filters.append("noise=alls=5:allf=t+u")

    return filters
