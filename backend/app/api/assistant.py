from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404, get_project_or_404
from app.database import models as m
from app.database.session import SessionLocal, get_db
from app.llm import runtime
from app.llm.orchestration.agent import resolve_model, run_turn
from app.llm.providers.grok import get_provider
from app.schemas.api import ChatIn, ConversationIn
from app.services import queries

router = APIRouter(prefix="/assistant", tags=["assistant"])


def conv_dict(c: m.Conversation, with_messages: bool = False) -> dict:
    d = {"id": c.id, "project_id": c.project_id, "title": c.title, "provider": c.provider, "model": c.model, "created_at": c.created_at.isoformat()}
    if with_messages:
        d["messages"] = [{"id": x.id, "role": x.role, "content": x.content, "provider": x.provider, "model": x.model,
                          "actions": x.actions, "created_at": x.created_at.isoformat()} for x in c.messages]
        d["tool_executions"] = [{"tool": t.tool_name, "arguments": t.arguments, "summary": t.result_summary, "ok": t.ok}
                                for t in c.__dict__.get("_tools", [])]
    return d


@router.get("/providers")
async def providers():
    e = runtime.effective()
    out = {}
    for name in ("ollama", "grok"):
        p = get_provider(name)
        st = await p.status()
        models = await p.list_models() if st.get("available") else []
        out[name] = {**st, "models": models, "selected_model": e["ollama_model"] if name == "ollama" else e["xai_model"] or None}
    return {"default": e["provider"], "providers": out,
            "deterministic_fallback": "Reports, exports and dashboards work without any LLM provider."}


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationIn, db: Session = Depends(get_db)):
    if body.project_id: get_project_or_404(body.project_id, db)
    prov = body.provider or runtime.effective()["provider"]
    c = m.Conversation(project_id=body.project_id, provider=prov, model=resolve_model(prov, body.model))
    db.add(c); db.commit()
    return conv_dict(c)


@router.get("/conversations")
def list_conversations(project_id: str, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    return [conv_dict(c) for c in db.query(m.Conversation).filter_by(project_id=project_id).order_by(m.Conversation.created_at.desc()).limit(50).all()]


@router.get("/conversations/{cid}")
def get_conversation(cid: str, db: Session = Depends(get_db)):
    c = db.get(m.Conversation, cid)
    if not c: raise HTTPException(404, "Conversation not found")
    d = conv_dict(c, True)
    d["tool_executions"] = [{"tool": t.tool_name, "arguments": t.arguments, "summary": t.result_summary, "ok": t.ok}
                            for t in db.query(m.ToolExecution).filter_by(conversation_id=cid).order_by(m.ToolExecution.id).all()]
    return d


@router.delete("/conversations/{cid}")
def clear_conversation(cid: str, db: Session = Depends(get_db)):
    c = db.get(m.Conversation, cid)
    if not c: raise HTTPException(404, "Conversation not found")
    db.delete(c); db.commit()
    return {"deleted": cid}


def _ctx(db: Session, c: m.Conversation, body: ChatIn) -> dict:
    ctx = dict(body.ui_context or {})
    if body.analysis_id:
        an = get_analysis_or_404(db, body.analysis_id)
        if an.project_id != c.project_id: raise HTTPException(403, "Analysis belongs to a different project")
        ctx.update(analysis_id=an.id, before_date=an.before_obs.acquisition_date.isoformat(), after_date=an.after_obs.acquisition_date.isoformat())
    ctx["project_id"] = c.project_id
    return ctx


@router.post("/conversations/{cid}/messages")
async def send_message(cid: str, body: ChatIn, db: Session = Depends(get_db)):
    """Streams Server-Sent Events: tool_start | tool_result | token | action | done | error."""
    c = db.get(m.Conversation, cid)
    if not c: raise HTTPException(404, "Conversation not found")
    prov = body.provider or c.provider; model = resolve_model(prov, body.model or c.model)
    c.provider, c.model = prov, model; db.commit()
    ctx = _ctx(db, c, body)

    async def gen():
        with SessionLocal() as sdb:
            conv = sdb.get(m.Conversation, cid)
            async for ev in run_turn(sdb, conv, body.message, ctx, prov, model):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
    if body.stream:
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    events = []
    async for chunk in gen():
        events.append(json.loads(chunk[6:]))
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")
    return {"answer": text, "events": [e for e in events if e["type"] != "token"]}


@router.get("/offline-summary/{analysis_id}")
def offline_summary(analysis_id: str, db: Session = Depends(get_db)):
    """Deterministic, LLM-free plain-text summary built from stored records (works without Ollama/Grok)."""
    an = get_analysis_or_404(db, analysis_id)
    s = queries.analysis_summary(db, an)
    if an.status != "completed": raise HTTPException(409, f"Analysis is {an.status}")
    rs = s["review_status_counts"]
    top = db.query(m.Event).filter_by(analysis_id=an.id).order_by(m.Event.priority_score.desc()).limit(5).all()
    lines = [f"Analysis {an.id} compares {s['before_date']} with {s['after_date']}.",
             f"The model predicted {s['n_events']} candidate change events in {s['n_clusters']} clusters, covering {s['changed_pct']:.2f}% of the image"
             + (f" ({s['changed_area_m2']:.0f} m²)." if s['changed_area_m2'] else " (pixel area only; not georeferenced)."),
             f"Review status: {rs['pending']} pending, {rs['confirmed']} confirmed, {rs['rejected']} rejected, {rs['needs_investigation']} need investigation.",
             "Highest analytical priority: " + (", ".join(f"{e.label} (priority {e.priority_score}, confidence {e.conf_mean:.2f})" for e in top) or "none") + ".",
             s["caveat"]]
    return {"text": "\n".join(lines), "generated_by": "deterministic template (no LLM)"}
