from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class ProviderUnavailable(Exception):
    """Raised for any condition that stops the provider from answering. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamEvent:
    kind: str  # token | tool_calls | done
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def status(self) -> dict: ...

    @abstractmethod
    async def list_models(self) -> list[dict]: ...

    @abstractmethod
    def stream_chat(self, messages: list[dict], tools: list[dict], model: str) -> AsyncIterator[StreamEvent]: ...

    async def chat_json(self, messages: list[dict], model: str, schema: dict | None = None) -> str:
        """Single non-tool completion (used for narratives). Default: concatenate streamed tokens."""
        out = []
        async for ev in self.stream_chat(messages, [], model):
            if ev.kind == "token": out.append(ev.text)
        return "".join(out)
