from __future__ import annotations

from app.engine.scanner.frame_sampler import FrameStat


def summarize_style(stats: list[FrameStat]) -> dict:
    if not stats:
        return {
            "brightness": 0.5,
            "saturation": 0.5,
            "contrast": 0.5,
            "sharpness": 0.5,
            "color_grade": "neutral",
            "film_grain": False,
            "sharpen": True,
        }

    brightness = sum(stat.brightness for stat in stats) / len(stats)
    saturation = sum(stat.saturation for stat in stats) / len(stats)
    contrast = sum(stat.contrast for stat in stats) / len(stats)
    sharpness = sum(stat.sharpness for stat in stats) / len(stats)
    motion_noise = sum(stat.frame_diff for stat in stats) / len(stats)

    if brightness < 0.38 and contrast > 0.38:
        color_grade = "high_contrast_dark"
    elif contrast > 0.55:
        color_grade = "dark_cinematic"
    else:
        color_grade = "neutral"

    return {
        "brightness": round(brightness, 4),
        "saturation": round(saturation, 4),
        "contrast": round(contrast, 4),
        "sharpness": round(sharpness, 4),
        "motion_noise": round(motion_noise, 4),
        "color_grade": color_grade,
        "film_grain": motion_noise > 0.025 or contrast > 0.5,
        "sharpen": sharpness < 0.75,
    }
