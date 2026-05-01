from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from app.engine.core.models import (
    BeatMap,
    ClipMetadata,
    ClipMetadataSet,
    MomentMetadata,
    MomentMetadataSet,
    Effect,
    TemplateRecipe,
    TemplateSegment,
    Transition,
    Timeline,
    TimelineAudio,
    TimelineSegment,
)


def _nearest_beat(time: float, beat_map: BeatMap | None, tolerance: float) -> float:
    if not beat_map or not beat_map.beats:
        return time
    nearest = min(beat_map.beats, key=lambda beat: abs(beat - time))
    if abs(nearest - time) <= tolerance:
        return nearest
    return time


def _clip_matches_slot(clip: ClipMetadata, slot_type: str, required_type: str | None) -> float:
    score = clip.overall_score
    desired = required_type or slot_type
    moment_types = {moment.type for moment in clip.detected_moments}
    ai_tags = set(clip.ai_tags)
    ai_confidence = clip.ai_confidence or 0.0

    slot_tag_preferences = {
        "intro": {"stencil": 0.75, "studio_ambience": 0.65, "artist_client": 0.6, "needle_work": 0.25},
        "process": {"needle_work": 0.9, "closeup_detail": 0.75, "wiping": 0.4, "stencil": 0.25},
        "detail": {"closeup_detail": 0.9, "needle_work": 0.65, "final_reveal": 0.45},
        "transition": {"wiping": 0.85, "needle_work": 0.55, "closeup_detail": 0.3},
        "high_energy": {"needle_work": 0.75, "wiping": 0.7, "closeup_detail": 0.35},
        "reveal": {"final_reveal": 1.05, "closeup_detail": 0.45},
        "ending": {"final_reveal": 1.15, "artist_client": 0.35, "closeup_detail": 0.3},
    }
    desired_tag_preferences = {
        "final_reveal": {"final_reveal": 1.0},
        "motion": {"needle_work": 0.55, "wiping": 0.55},
        "process": {"needle_work": 0.75, "closeup_detail": 0.5},
        "detail": {"closeup_detail": 0.75},
    }

    for tag, weight in slot_tag_preferences.get(slot_type, {}).items():
        if tag in ai_tags:
            score += weight * max(0.35, ai_confidence)
    for tag, weight in desired_tag_preferences.get(desired, {}).items():
        if tag in ai_tags:
            score += weight * max(0.35, ai_confidence)

    if desired in {"motion", "high_motion", "high_energy"}:
        score += clip.motion_score * 0.4
    if desired in {"detail", "close-up", "process", "needle", "needle/work"}:
        score += clip.sharpness_score * 0.25
    if desired in {"final_reveal", "reveal", "wipe_end", "ending"}:
        score += 0.5 if {"final_reveal", "wipe_end"} & moment_types else clip.sharpness_score * 0.2
    if slot_type in {"intro", "transition"}:
        score += clip.sharpness_score * 0.15

    if clip.is_blurry:
        score -= 0.45
    if clip.is_too_dark:
        score -= 0.25
    if "unusable" in ai_tags or clip.best_use == "unused":
        score -= 1.2
    return score


def _pick_clip(
    clips: list[ClipMetadata],
    slot_type: str,
    required_type: str | None,
    used_counts: dict[str, int],
    previous_clip_id: str | None,
    segment_index: int,
    segment_count: int,
) -> ClipMetadata:
    usable = [
        clip
        for clip in clips
        if not clip.is_too_dark and "unusable" not in set(clip.ai_tags) and clip.best_use != "unused"
    ] or [clip for clip in clips if not clip.is_too_dark] or clips

    if segment_index >= max(0, segment_count - 2):
        reveal_clips = [clip for clip in usable if "final_reveal" in set(clip.ai_tags)]
        if reveal_clips:
            usable = reveal_clips

    return max(
        usable,
        key=lambda clip: (
            _clip_matches_slot(clip, slot_type, required_type)
            - used_counts[clip.clip_id] * 0.8
            - (0.9 if clip.clip_id == previous_clip_id else 0.0),
            clip.duration,
        ),
    )


def _source_range(clip: ClipMetadata, duration: float, used_counts: dict[str, int]) -> tuple[float, float]:
    usable_duration = max(0.1, clip.duration)
    if usable_duration <= duration:
        return 0.0, usable_duration
    max_start = usable_duration - duration
    offset_fraction = (used_counts[clip.clip_id] % 4) / 4
    start = max_start * offset_fraction
    return start, start + duration


def _moment_matches_segment(moment: MomentMetadata, clip: ClipMetadata, segment: TemplateSegment) -> float:
    score = moment.score
    tags = set(clip.ai_tags)
    desired = segment.required_clip_type or segment.slot_type
    moment_type = moment.moment_type

    if segment.slot_type in {"high_energy", "transition"} or desired == "motion":
        score += moment.motion_score * 0.55
        if moment_type in {"needle_work", "wiping", "transition"}:
            score += 0.28
    if segment.slot_type in {"process", "detail"}:
        score += moment.sharpness_score * 0.35 + moment.stability_score * 0.18
        if moment_type in {"needle_work", "detail", "process"}:
            score += 0.24
    if segment.slot_type in {"intro"}:
        if moment_type == "intro" or {"stencil", "artist_client", "studio_ambience"} & tags:
            score += 0.35
        score += moment.stability_score * 0.15
    if segment.slot_type in {"reveal", "ending"} or desired == "final_reveal":
        if moment_type == "reveal_candidate" or "final_reveal" in tags:
            score += 0.75
        score += moment.stability_score * 0.25 + moment.sharpness_score * 0.2

    if "unusable" in tags or clip.best_use == "unused":
        score -= 1.0
    return score


def _pick_moment(
    moments: MomentMetadataSet | None,
    clips_by_id: dict[str, ClipMetadata],
    segment: TemplateSegment,
    duration: float,
    used_moment_ids: set[str],
    used_counts: dict[str, int],
    previous_clip_id: str | None,
    segment_count: int,
) -> MomentMetadata | None:
    if not moments:
        return None
    min_duration = max(0.12, duration * 0.88)
    candidates = [
        moment
        for moment in moments.moments
        if moment.moment_id not in used_moment_ids
        and moment.clip_id in clips_by_id
        and moment.duration >= min_duration
    ]
    if not candidates:
        candidates = [
            moment
            for moment in moments.moments
            if moment.moment_id not in used_moment_ids
            and moment.clip_id in clips_by_id
        ]
    if not candidates:
        return None

    if segment.index >= max(0, segment_count - 2):
        reveal_candidates = [
            moment
            for moment in candidates
            if moment.moment_type == "reveal_candidate"
            or "final_reveal" in set(clips_by_id[moment.clip_id].ai_tags)
        ]
        if reveal_candidates:
            candidates = reveal_candidates
    elif segment.slot_type == "intro":
        intro_candidates = [
            moment
            for moment in candidates
            if moment.moment_type == "intro"
            or {"stencil", "artist_client", "studio_ambience"} & set(clips_by_id[moment.clip_id].ai_tags)
        ]
        if intro_candidates:
            candidates = intro_candidates

    return max(
        candidates,
        key=lambda moment: (
            _moment_matches_segment(moment, clips_by_id[moment.clip_id], segment)
            - used_counts[moment.clip_id] * 0.38
            - (0.45 if moment.clip_id == previous_clip_id else 0.0),
            moment.duration,
        ),
    )


def _pro_effect_for_segment(segment: TemplateSegment, segment_count: int) -> tuple[Effect, Transition]:
    duration = segment.duration
    intensity = segment.effect.intensity if segment.effect.intensity is not None else 0.65
    metadata = {
        **segment.effect.metadata,
        "source_effect": segment.effect.type,
        "pro_effect_layer": True,
    }
    transition_metadata = {
        **segment.transition_out.metadata,
        "source_transition": segment.transition_out.type,
        "pro_effect_layer": True,
    }
    is_late = segment.index >= max(0, segment_count - 2)
    is_reveal = segment.slot_type in {"reveal", "ending"} or is_late
    is_fast = duration <= 0.42 or segment.slot_type in {"high_energy", "transition"}
    has_flash_note = any("flash=" in note for note in segment.scanner_notes)
    scanner_effects = {
        "impact_zoom",
        "rgb_glitch",
        "motion_blur",
        "speed_ramp",
        "whip_pan",
        "rotate_shake",
        "blur_zoom",
        "strobe",
        "vhs_noise",
        "pixel_punch",
        "vignette_focus",
    }
    scanner_transitions = {"glitch", "flash_hit", "white_hit", "black_hit", "red_hit", "invert_hit", "blur_hit", "strobe_hit"}

    if is_reveal:
        effect = Effect(type="slow_zoom", intensity=0.45, zoom_end=1.06, metadata=metadata)
        transition = Transition(type="cut", metadata=transition_metadata)
        return effect, transition

    if is_fast:
        cycle = segment.index % 8
        if cycle == 0:
            effect_type = "impact_zoom"
        elif cycle == 1:
            effect_type = "rgb_glitch"
        elif cycle == 2:
            effect_type = "motion_blur"
        elif cycle == 3:
            effect_type = "speed_ramp"
        elif cycle == 4:
            effect_type = "whip_pan"
        elif cycle == 5:
            effect_type = "rotate_shake"
        elif cycle == 6:
            effect_type = "pixel_punch"
        else:
            effect_type = "strobe"
        if segment.effect.type in scanner_effects:
            effect_type = segment.effect.type
        effect = Effect(type=effect_type, intensity=max(0.55, intensity), metadata=metadata)
        if segment.transition_out.type in scanner_transitions:
            hit_type = segment.transition_out.type
        else:
            hit_type = "flash_hit" if has_flash_note else ["black_hit", "white_hit", "red_hit", "invert_hit"][segment.index % 4]
        transition = Transition(type=hit_type, duration=0.055, metadata=transition_metadata)
        return effect, transition

    if segment.effect.type in scanner_effects:
        effect = Effect(type=segment.effect.type, intensity=max(0.45, intensity), metadata=metadata)
    elif segment.effect.type in {"zoom_punch", "slow_zoom"}:
        effect = Effect(type="impact_zoom", intensity=max(0.55, intensity), metadata=metadata)
    else:
        effect = Effect(type="slow_zoom", intensity=0.35, zoom_end=1.045, metadata=metadata)

    transition_type = segment.transition_out.type if segment.transition_out.type in scanner_transitions else ("flash_hit" if has_flash_note else "cut")
    transition = Transition(type=transition_type, duration=0.05 if transition_type != "cut" else None, metadata=transition_metadata)
    return effect, transition


def build_timeline(
    template: TemplateRecipe,
    clip_metadata: ClipMetadataSet,
    song_path: Path,
    output_path: Path,
    *,
    beat_map: BeatMap | None = None,
    audio_start: float = 0.0,
    moments: MomentMetadataSet | None = None,
) -> Timeline:
    if not clip_metadata.clips:
        raise ValueError("Cannot build timeline without clips")

    sorted_clips = sorted(clip_metadata.clips, key=lambda clip: clip.overall_score, reverse=True)
    clips_by_id = {clip.clip_id: clip for clip in clip_metadata.clips}
    used_counts: dict[str, int] = defaultdict(int)
    used_moment_ids: set[str] = set()
    planned_segments: list[TimelineSegment] = []

    current_time = 0.0
    previous_clip_id: str | None = None
    for template_segment in template.segments:
        duration = template_segment.duration
        if template.beat_sync:
            aligned_end = _nearest_beat(
                current_time + duration,
                beat_map,
                template.beat_sync_tolerance,
            )
            if aligned_end > current_time + 0.15:
                duration = aligned_end - current_time

        effect, transition_out = _pro_effect_for_segment(template_segment, len(template.segments))
        source_duration = duration * 1.18 if effect.type == "speed_ramp" else duration
        moment = _pick_moment(
            moments,
            clips_by_id,
            template_segment,
            source_duration,
            used_moment_ids,
            used_counts,
            previous_clip_id,
            len(template.segments),
        )
        if moment:
            clip = clips_by_id[moment.clip_id]
            source_start = moment.start
            source_end = min(moment.end, source_start + source_duration)
            if source_end - source_start < min(source_duration, clip.duration):
                source_end = min(clip.duration, source_start + source_duration)
            used_moment_ids.add(moment.moment_id)
        else:
            clip = _pick_clip(
                sorted_clips,
                template_segment.slot_type,
                template_segment.required_clip_type,
                used_counts,
                previous_clip_id,
                template_segment.index,
                len(template.segments),
            )
            source_start, source_end = _source_range(clip, source_duration, used_counts)
        if effect.type == "speed_ramp":
            effect = effect.model_copy(
                update={"metadata": {**effect.metadata, "source_duration": source_end - source_start}}
            )
        used_counts[clip.clip_id] += 1
        timeline_end = round(current_time + duration, 6)
        previous_clip_id = clip.clip_id

        planned_segments.append(
            TimelineSegment(
                segment_index=template_segment.index,
                clip_id=clip.clip_id,
                source_file=clip.path,
                source_start=source_start,
                source_end=source_end,
                timeline_start=current_time,
                timeline_end=timeline_end,
                effect=effect,
                transition_out=transition_out,
                moment_id=moment.moment_id if moment else None,
                crop=moment.crop if moment else None,
            )
        )
        current_time = round(timeline_end, 6)

    return Timeline(
        job_id=clip_metadata.job_id,
        template_id=template.template_id,
        output_file=output_path,
        resolution=template.resolution,
        fps=template.fps,
        timeline=planned_segments,
        audio=TimelineAudio(file=song_path, start=audio_start, end=audio_start + current_time),
        global_style=template.global_style.model_copy(
            update={"color_grade": "cinematic_grade", "sharpen": True, "film_grain": True}
        ),
    )
