from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from app.core.config import get_settings
from app.llm import runtime
from app.llm.providers.base import LLMProvider, ProviderUnavailable, StreamEvent, ToolCall

log = logging.getLogger("terratrace.grok")


class GrokProvider(LLMProvider):
    """xAI API (OpenAI-compatible chat completions). The API key is read from the environment only and never logged."""
    name = "grok"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, max_retries: int = 2):
        s = get_settings()
        self._key, self._base = s.xai_api_key, s.xai_base_url.rstrip("/")
        self._transport, self._timeout, self._retries = transport, s.llm_timeout_s, max_retries

    def _headers(self):
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def _client(self, timeout=None):
        return httpx.AsyncClient(base_url=self._base, timeout=timeout or self._timeout, transport=self._transport)

    async def status(self) -> dict:
        if not self._key:
            return {"available": False, "code": "missing_api_key", "message": "XAI_API_KEY is not set. Grok is optional; Ollama or deterministic reports work without it."}
        try:
            async with self._client(8) as c:
                r = await c.get("/models", headers=self._headers())
            if r.status_code == 401: return {"available": False, "code": "invalid_api_key", "message": "xAI rejected the API key."}
            return {"available": r.status_code == 200, "base_url": self._base}
        except httpx.HTTPError as e:
            return {"available": False, "code": "unreachable", "message": f"xAI API unreachable: {type(e).__name__}"}

    async def list_models(self) -> list[dict]:
        if not self._key: return []
        try:
            async with self._client(8) as c:
                r = await c.get("/models", headers=self._headers()); r.raise_for_status()
                return [{"name": m["id"]} for m in r.json().get("data", [])]
        except httpx.HTTPError:
            return []

    async def stream_chat(self, messages, tools, model) -> AsyncIterator[StreamEvent]:
        if not self._key:
            raise ProviderUnavailable("missing_api_key", "XAI_API_KEY is not configured on the server.")
        if not model:
            raise ProviderUnavailable("no_model_configured", "No Grok model selected. Set XAI_MODEL or choose one in Settings.")
        payload = {"model": model, "messages": messages, "stream": True, "temperature": 0.1}
        if tools: payload["tools"] = tools
        attempt = 0
        while True:
            try:
                acc: dict[int, dict] = {}
                async with self._client() as c:
                    async with c.stream("POST", "/chat/completions", json=payload, headers=self._headers()) as r:
                        if r.status_code in (429, 500, 502, 503, 504) and attempt < self._retries:
                            delay = float(r.headers.get("retry-after", 2 ** attempt)); attempt += 1
                            log.warning("xAI HTTP %s, retry %s in %.1fs", r.status_code, attempt, delay)
                            await asyncio.sleep(min(delay, 10)); continue
                        if r.status_code == 401: raise ProviderUnavailable("invalid_api_key", "xAI rejected the API key.")
                        if r.status_code == 429: raise ProviderUnavailable("rate_limited", "xAI rate limit reached. Try again shortly.")
                        if r.status_code == 404: raise ProviderUnavailable("model_not_found", f"Model '{model}' not found for this xAI key.")
                        if r.status_code != 200:
                            raise ProviderUnavailable("provider_error", f"xAI error {r.status_code}")
                        usage = {}
                        async for line in r.aiter_lines():
                            if not line.startswith("data:"): continue
                            data = line[5:].strip()
                            if data == "[DONE]": break
                            d = json.loads(data)
                            usage = d.get("usage") or usage
                            for ch in d.get("choices", []):
                                delta = ch.get("delta", {})
                                if delta.get("content"): yield StreamEvent("token", delta["content"])
                                for tc in delta.get("tool_calls") or []:
                                    e = acc.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                                    e["id"] = tc.get("id") or e["id"]
                                    fn = tc.get("function", {})
                                    e["name"] = fn.get("name") or e["name"]; e["args"] += fn.get("arguments") or ""
                        calls = []
                        for _, e in sorted(acc.items()):
                            try: args = json.loads(e["args"] or "{}")
                            except Exception: args = {}
                            calls.append(ToolCall(e["id"] or f"call_{len(calls)}", e["name"], args))
                        if calls: yield StreamEvent("tool_calls", tool_calls=calls)
                        log.info("xAI usage model=%s %s", model, {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")})
                        yield StreamEvent("done", usage=usage)
                        return
            except httpx.TimeoutException as e:
                raise ProviderUnavailable("timeout", "xAI request timed out") from e
            except httpx.HTTPError as e:
                raise ProviderUnavailable("unreachable", f"xAI API unreachable: {type(e).__name__}") from e


def get_provider(name: str, transport=None) -> LLMProvider:
    from app.llm.providers.ollama import OllamaProvider
    if name == "grok": return GrokProvider(transport=transport)
    if name == "ollama": return OllamaProvider(transport=transport)
    raise ValueError(f"unknown provider {name}")
