"""Tool registry: the ONLY way the LLM touches TerraTrace data.

Every tool has a Pydantic argument model; arguments are validated before execution and results are returned as
plain JSON plus an optional list of UI actions (validated again by the frontend allowlist). Tools are read-only
except report generation (creates a new report). No tool can change review status, delete data, run SQL/shell/Python.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.database import models as m

ALLOWED_ACTION_TYPES = {"filter_events", "open_event", "select_cluster", "show_comparison", "navigate_analysis",
                        "open_report", "show_pending_review", "highlight_events"}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(s: Any, limit: int = 300) -> str:
    """Untrusted strings (filenames, notes, labels) are stripped of control chars and truncated before reaching the LLM."""
    return _CTRL.sub("", str(s))[:limit]


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    project_id: str
    analysis_id: str | None = None
    ui_context: dict = field(default_factory=dict)

    def analysis(self, analysis_id: str | None) -> m.Analysis:
        aid = analysis_id or self.analysis_id
        if not aid:
            raise ToolError("No analysis selected. Specify analysis_id or select an analysis in the workspace.")
        an = self.db.get(m.Analysis, aid)
        if not an or an.project_id != self.project_id:  # project isolation enforced on every call
            raise ToolError(f"Analysis {aid} not found in the active project")
        return an

    def project(self) -> m.Project:
        p = self.db.get(m.Project, self.project_id)
        if not p: raise ToolError("Active project not found")
        return p


@dataclass
class ToolResult:
    data: Any
    summary: str
    actions: list[dict] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[ToolContext, Any], ToolResult]
    read_only: bool = True

    def spec(self) -> dict:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        for p in schema.get("properties", {}).values(): p.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": schema}}


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, args_model: type[BaseModel], read_only: bool = True):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, args_model, fn, read_only)
        return fn
    return deco


def tool_specs() -> list[dict]:
    return [t.spec() for t in REGISTRY.values()]


def execute(ctx: ToolContext, name: str, arguments: dict) -> ToolResult:
    t = REGISTRY.get(name)
    if t is None:
        raise ToolError(f"Unknown tool '{name}'. Allowed tools: {', '.join(sorted(REGISTRY))}")
    try:
        args = t.args_model.model_validate(arguments or {})
    except ValidationError as e:
        raise ToolError(f"Invalid arguments for {name}: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from e
    res = t.fn(ctx, args)
    res.actions = [a for a in res.actions if a.get("type") in ALLOWED_ACTION_TYPES]
    return res
