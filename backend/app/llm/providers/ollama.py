from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.llm import runtime
from app.llm.providers.base import LLMProvider, ProviderUnavailable, StreamEvent, ToolCall


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or runtime.effective()["ollama_base_url"]).rstrip("/")
        self._transport = transport
        self._timeout = get_settings().llm_timeout_s

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout or self._timeout, transport=self._transport)

    async def status(self) -> dict:
        try:
            async with self._client(5) as c:
                r = await c.get("/api/version")
                r.raise_for_status()
                return {"available": True, "version": r.json().get("version"), "base_url": self.base_url}
        except (httpx.HTTPError, OSError) as e:
            return {"available": False, "base_url": self.base_url, "code": "unreachable",
                    "message": f"Ollama is not reachable at {self.base_url}. Install from https://ollama.com, run `ollama serve`, "
                               f"and pull a tool-capable model (see docs/ollama-setup.md). Detail: {type(e).__name__}"}

    async def list_models(self) -> list[dict]:
        try:
            async with self._client(8) as c:
                r = await c.get("/api/tags"); r.raise_for_status()
                return [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2), "parameter_size": m.get("details", {}).get("parameter_size")}
                        for m in r.json().get("models", [])]
        except (httpx.HTTPError, OSError):
            return []

    async def stream_chat(self, messages, tools, model) -> AsyncIterator[StreamEvent]:
        if not model:
            raise ProviderUnavailable("no_model_configured", "No Ollama model selected. Set OLLAMA_MODEL or choose one in Settings.")
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": 0.1}}
        if tools: payload["tools"] = tools
        calls: list[ToolCall] = []
        try:
            async with self._client() as c:
                async with c.stream("POST", "/api/chat", json=payload) as r:
                    if r.status_code != 200:
                        body = (await r.aread()).decode("utf-8", "ignore")[:300]
                        if r.status_code == 404 or "not found" in body.lower():
                            raise ProviderUnavailable("model_not_installed", f"Model '{model}' is not installed in Ollama. Run: ollama pull {model}")
                        if "does not support tools" in body.lower():
                            raise ProviderUnavailable("tools_unsupported", f"Model '{model}' does not support tool calling. Choose a tool-capable model (docs/ollama-setup.md).")
                        raise ProviderUnavailable("provider_error", f"Ollama error {r.status_code}: {body}")
                    async for line in r.aiter_lines():
                        if not line.strip(): continue
                        d = json.loads(line)
                        msg = d.get("message") or {}
                        if msg.get("content"):
                            yield StreamEvent("token", msg["content"])
                        for tc in msg.get("tool_calls") or []:
                            fn = tc.get("function", {})
                            args = fn.get("arguments") or {}
                            if isinstance(args, str):
                                try: args = json.loads(args)
                                except Exception: args = {}
                            calls.append(ToolCall(tc.get("id") or f"call_{uuid.uuid4().hex[:8]}", fn.get("name", ""), args))
                        if d.get("done"):
                            if calls: yield StreamEvent("tool_calls", tool_calls=calls)
                            yield StreamEvent("done", usage={"prompt_tokens": d.get("prompt_eval_count"), "completion_tokens": d.get("eval_count")})
        except httpx.ConnectError as e:
            raise ProviderUnavailable("unreachable", f"Cannot connect to Ollama at {self.base_url}. Is `ollama serve` running?") from e
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("timeout", "Ollama timed out. Large models can be slow on CPU; try a smaller model.") from e
