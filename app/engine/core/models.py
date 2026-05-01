from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Resolution(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Effect(BaseModel):
    type: str = "none"
    zoom_start: float | None = None
    zoom_end: float | None = None
    intensity: float | None = None
    duration: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Transition(BaseModel):
    type: str = "cut"
    duration: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TemplateSegment(BaseModel):
    index: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)
    slot_type: str = "process"
    required_clip_type: str | None = None
    effect: Effect = Field(default_factory=Effect)
    transition_out: Transition = Field(default_factory=Transition)
    source_start: float | None = Field(default=None, ge=0)
    source_end: float | None = Field(default=None, ge=0)
    scanner_confidence: float | None = Field(default=None, ge=0, le=1)
    scanner_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timing(self) -> "TemplateSegment":
        actual = self.end - self.start
        if actual <= 0:
            raise ValueError("segment end must be greater than start")
        if abs(actual - self.duration) > 0.02:
            raise ValueError("segment duration must match end - start")
        return self


class GlobalStyle(BaseModel):
    color_grade: str | None = None
    film_grain: bool = False
    sharpen: bool = False


class TemplateRecipe(BaseModel):
    template_id: str
    name: str
    version: str = "1.0"
    aspect_ratio: Literal["9:16"] = "9:16"
    resolution: Resolution = Field(default_factory=lambda: Resolution(width=1080, height=1920))
    fps: int = Field(default=30, gt=0)
    total_duration: float = Field(gt=0)
    music_mode: str = "user_song"
    beat_sync: bool = False
    beat_sync_tolerance: float = Field(default=0.12, ge=0)
    segments: list[TemplateSegment]
    global_style: GlobalStyle = Field(default_factory=GlobalStyle)
    scanner_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("segments")
    @classmethod
    def require_segments(cls, segments: list[TemplateSegment]) -> list[TemplateSegment]:
        if not segments:
            raise ValueError("template requires at least one segment")
        return segments


class DetectedMoment(BaseModel):
    time: float = Field(ge=0)
    type: str
    score: float = Field(ge=0, le=1)


class ClipMetadata(BaseModel):
    clip_id: str
    filename: str
    path: Path
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    overall_score: float = Field(ge=0, le=1)
    sharpness_score: float = Field(ge=0, le=1)
    brightness_score: float = Field(ge=0, le=1)
    motion_score: float = Field(ge=0, le=1)
    is_blurry: bool = False
    is_too_dark: bool = False
    detected_moments: list[DetectedMoment] = Field(default_factory=list)
    ai_tags: list[str] = Field(default_factory=list)
    ai_description: str | None = None
    ai_confidence: float | None = Field(default=None, ge=0, le=1)
    best_use: str | None = None
    ai_tag_source: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ClipMetadataSet(BaseModel):
    job_id: str = "local_job"
    clips: list[ClipMetadata]


class CropMetadata(BaseModel):
    crop_x: float = Field(default=0.5, ge=0, le=1)
    crop_y: float = Field(default=0.5, ge=0, le=1)
    crop_zoom: float = Field(default=1.0, ge=1.0, le=2.0)
    framing_confidence: float = Field(default=0.0, ge=0, le=1)


class MomentMetadata(BaseModel):
    moment_id: str
    clip_id: str
    source_file: Path
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)
    moment_type: str = "process"
    score: float = Field(ge=0, le=1)
    sharpness_score: float = Field(ge=0, le=1)
    brightness_score: float = Field(ge=0, le=1)
    motion_score: float = Field(ge=0, le=1)
    stability_score: float = Field(ge=0, le=1)
    crop: CropMetadata = Field(default_factory=CropMetadata)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_ranges(self) -> "MomentMetadata":
        if self.end <= self.start:
            raise ValueError("moment end must be greater than start")
        if abs((self.end - self.start) - self.duration) > 0.02:
            raise ValueError("moment duration must match end - start")
        return self


class MomentMetadataSet(BaseModel):
    job_id: str = "local_job"
    moments: list[MomentMetadata]


class EnergyPeak(BaseModel):
    time: float = Field(ge=0)
    strength: float = Field(ge=0, le=1)
    type: str = "energy_peak"


class BeatMap(BaseModel):
    audio_file: str
    duration: float = Field(ge=0)
    bpm: float = Field(ge=0)
    beats: list[float] = Field(default_factory=list)
    strong_beats: list[float] = Field(default_factory=list)
    energy_peaks: list[EnergyPeak] = Field(default_factory=list)


class TimelineSegment(BaseModel):
    segment_index: int = Field(ge=0)
    clip_id: str
    source_file: Path
    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    timeline_start: float = Field(ge=0)
    timeline_end: float = Field(gt=0)
    effect: Effect = Field(default_factory=Effect)
    transition_out: Transition = Field(default_factory=Transition)
    moment_id: str | None = None
    crop: CropMetadata | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_ranges(self) -> "TimelineSegment":
        if self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        if self.timeline_end <= self.timeline_start:
            raise ValueError("timeline_end must be greater than timeline_start")
        return self

    @property
    def duration(self) -> float:
        return self.timeline_end - self.timeline_start


class TimelineAudio(BaseModel):
    file: Path
    start: float = Field(default=0, ge=0)
    end: float = Field(gt=0)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Timeline(BaseModel):
    job_id: str = "local_job"
    template_id: str
    output_file: Path
    resolution: Resolution
    fps: int = Field(default=30, gt=0)
    timeline: list[TimelineSegment]
    audio: TimelineAudio
    global_style: GlobalStyle = Field(default_factory=GlobalStyle)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def model_to_jsonable(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json")
