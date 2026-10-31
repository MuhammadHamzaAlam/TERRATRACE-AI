from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class AOIIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geometry: dict

    @field_validator("geometry")
    @classmethod
    def _poly(cls, v):
        from shapely.geometry import shape
        try:
            g = shape(v)
        except Exception as e:
            raise ValueError(f"Invalid GeoJSON geometry: {e}")
        if g.geom_type not in ("Polygon", "MultiPolygon") or not g.is_valid or g.is_empty:
            raise ValueError("AOI must be a valid, non-empty Polygon/MultiPolygon in EPSG:4326")
        minx, miny, maxx, maxy = g.bounds
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise ValueError("AOI coordinates must be lon/lat (EPSG:4326)")
        return v


class AnalysisIn(BaseModel):
    before_observation_id: str
    after_observation_id: str
    threshold: float = Field(default=0.5, ge=0.05, le=0.95)
    min_event_pixels: int = Field(default=20, ge=1, le=100000)
    cluster_eps: float | None = Field(default=None, gt=0)
    cluster_min_samples: int = Field(default=2, ge=1, le=50)
    allow_domain_gap: bool = False
    allow_misaligned: bool = False
    priority_weights: dict[str, float] | None = None
    start: bool = True


class ReviewIn(BaseModel):
    status: Literal["pending", "confirmed", "rejected", "needs_investigation"]
    notes: str = Field(default="", max_length=4000)


class BulkReviewIn(ReviewIn):
    event_ids: list[str]
    confirm: bool = False


class ReportIn(BaseModel):
    kind: Literal["analysis", "comparison"] = "analysis"
    analysis_id: str | None = None
    compare_analysis_id: str | None = None
    with_narrative: bool = False


class TrainIn(BaseModel):
    epochs: int = Field(default=8, ge=1, le=200)
    batch_size: int = Field(default=8, ge=1, le=128)
    lr: float = Field(default=5e-4, gt=0, lt=1)
    crops_per_image: int = Field(default=2, ge=1, le=16)
    confirm: bool = False


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    analysis_id: str | None = None
    provider: Literal["ollama", "grok"] | None = None
    model: str | None = None
    ui_context: dict[str, Any] = {}
    stream: bool = False


class ConversationIn(BaseModel):
    project_id: str | None = None
    provider: Literal["ollama", "grok"] | None = None
    model: str | None = None
