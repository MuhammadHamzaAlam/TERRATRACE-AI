"""Runtime (non-secret) LLM settings. Secrets (XAI_API_KEY) come only from the environment and are never persisted/returned.
The Ollama base URL is intentionally NOT changeable at runtime (SSRF protection): set OLLAMA_BASE_URL in the environment."""
from __future__ import annotations

import json
from pathlib import Path

from app.core.config import REPO_ROOT, get_settings

_FILE = REPO_ROOT / "data" / "runtime_settings.json"
PROVIDERS = ("ollama", "grok")


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text())
    except Exception:
        return {}


def get(key: str, default=None):
    return _load().get(key, default)


def update(provider: str | None = None, ollama_model: str | None = None, xai_model: str | None = None, ollama_base_url: str | None = None):
    if ollama_base_url is not None:
        raise ValueError("The Ollama base URL can only be set via the OLLAMA_BASE_URL environment variable")
    cur = _load()
    if provider is not None:
        if provider not in PROVIDERS: raise ValueError(f"provider must be one of {PROVIDERS}")
        cur["provider"] = provider
    for k, v in (("ollama_model", ollama_model), ("xai_model", xai_model)):
        if v is not None:
            v = v.strip()
            if len(v) > 100 or any(c in v for c in " \n\t;|&$`"): raise ValueError(f"invalid {k}")
            cur[k] = v
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(cur))


def effective() -> dict:
    s, r = get_settings(), _load()
    return {"provider": r.get("provider", s.llm_provider), "ollama_base_url": s.ollama_base_url,
            "ollama_model": r.get("ollama_model", s.ollama_model), "xai_model": r.get("xai_model", s.xai_model),
            "xai_configured": bool(s.xai_api_key)}


def configured_summary() -> dict:
    e = effective()
    return {"provider": e["provider"], "ollama": {"base_url": e["ollama_base_url"], "model": e["ollama_model"] or None},
            "grok": {"api_key_configured": e["xai_configured"], "model": e["xai_model"] or None}}
