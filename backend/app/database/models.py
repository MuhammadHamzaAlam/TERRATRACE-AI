"""SQLAlchemy models. Portable SQL only (JSON columns, no SQLite-specific features) so PostgreSQL is feasible."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("PRJ"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(100), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    observations = relationship("Observation", back_populates="project", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="project", cascade="all, delete-orphan")
    aois = relationship("AOI", back_populates="project", cascade="all, delete-orphan")


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("OBS"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    acquisition_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50), default="upload")  # upload | sentinel2
    file_path: Mapped[str] = mapped_column(String(500))
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(300), default="")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    band_count: Mapped[int] = mapped_column(Integer, default=3)
    georeferenced: Mapped[bool] = mapped_column(Boolean, default=False)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transform: Mapped[list | None] = mapped_column(JSON, nullable=True)  # affine a,b,c,d,e,f
    bounds_wgs84: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [minx,miny,maxx,maxy]
    pixel_size_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    project = relationship("Project", back_populates="observations")


class AOI(Base):
    __tablename__ = "aois"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("AOI"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    geometry: Mapped[dict] = mapped_column(JSON)  # GeoJSON geometry, EPSG:4326
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    project = relationship("Project", back_populates="aois")


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("A"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    before_obs_id: Mapped[str] = mapped_column(ForeignKey("observations.id"))
    after_obs_id: Mapped[str] = mapped_column(ForeignKey("observations.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed|blocked
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    status_message: Mapped[str] = mapped_column(Text, default="")
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    alignment: Mapped[dict] = mapped_column(JSON, default=dict)
    compatibility: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    mask_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prob_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    overlay_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project = relationship("Project", back_populates="analyses")
    before_obs = relationship("Observation", foreign_keys=[before_obs_id])
    after_obs = relationship("Observation", foreign_keys=[after_obs_id])
    events = relationship("Event", back_populates="analysis", cascade="all, delete-orphan")
    clusters = relationship("Cluster", back_populates="analysis", cascade="all, delete-orphan")


class Cluster(Base):
    __tablename__ = "clusters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # CL-<analysis>-<n>
    label: Mapped[str] = mapped_column(String(32))  # CL-001
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    event_count: Mapped[int] = mapped_column(Integer)
    total_area_px: Mapped[float] = mapped_column(Float)
    total_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_px: Mapped[list] = mapped_column(JSON)
    centroid_geo: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extent_px: Mapped[list] = mapped_column(JSON)
    boundary_geo: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mean_confidence: Mapped[float] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis = relationship("Analysis", back_populates="clusters")


class EventTrack(Base):
    """A spatial track linking candidate events across analyses (temporal association)."""
    __tablename__ = "event_tracks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("TRK"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    first_observed: Mapped[date] = mapped_column(Date)
    last_observed: Mapped[date] = mapped_column(Date)
    n_observations: Mapped[int] = mapped_column(Integer, default=1)
    centroid_px: Mapped[list] = mapped_column(JSON)
    centroid_geo: Mapped[list | None] = mapped_column(JSON, nullable=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # EVT-<analysis>-<n>
    label: Mapped[str] = mapped_column(String(32))  # EVT-001
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    track_id: Mapped[str | None] = mapped_column(ForeignKey("event_tracks.id", ondelete="SET NULL"), nullable=True, index=True)
    bbox_px: Mapped[list] = mapped_column(JSON)  # x0,y0,x1,y1
    centroid_px: Mapped[list] = mapped_column(JSON)
    area_px: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_pct: Mapped[float] = mapped_column(Float, default=0.0)
    conf_mean: Mapped[float] = mapped_column(Float)
    conf_max: Mapped[float] = mapped_column(Float)
    conf_min: Mapped[float] = mapped_column(Float)
    geometry_geo: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # GeoJSON polygon, EPSG:4326
    centroid_geo: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [lon, lat]
    before_date: Mapped[date] = mapped_column(Date)
    after_date: Mapped[date] = mapped_column(Date)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    temporal_status: Mapped[str] = mapped_column(String(20), default="new")  # new|recurring
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analysis = relationship("Analysis", back_populates="events")
    history = relationship("EventHistory", back_populates="event", cascade="all, delete-orphan", order_by="EventHistory.id")

    __table_args__ = (Index("ix_events_analysis_conf", "analysis_id", "conf_mean"),)


class EventHistory(Base):
    """Audit trail: every review status change (and note) is appended, never mutated."""
    __tablename__ = "event_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    previous_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    reviewer: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    event = relationship("Event", back_populates="history")


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("RPT"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # analysis | comparison
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict] = mapped_column(JSON)  # deterministic structured data
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("MDL"))
    name: Mapped[str] = mapped_column(String(100))
    architecture: Mapped[str] = mapped_column(String(100), default="SiameseUNet-ResNet18")
    checkpoint_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="trained")
    dataset: Mapped[str] = mapped_column(String(100), default="LEVIR-CD")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)  # True only after test-set evaluation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrainingRun(Base):
    __tablename__ = "training_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("TRN"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str] = mapped_column(Text, default="")
    model_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("JOB"))
    kind: Mapped[str] = mapped_column(String(30))
    ref_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("CNV"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    provider: Mapped[str] = mapped_column(String(30), default="ollama")
    model: Mapped[str] = mapped_column(String(100), default="")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    conversation = relationship("Conversation", back_populates="messages")


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
