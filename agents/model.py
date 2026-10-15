"""Model client abstraction: OpenAI-compatible HTTP client and a scripted fake."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 2_000_000
THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


class ModelError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ModelReply:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens


class ModelClient(Protocol):
    def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int, timeout: float
    ) -> ModelReply: ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


# No proxy handler from the environment, no redirects: the bearer key and prompt
# text can only go to the configured host.
_DIRECT_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _RejectRedirects(),
)


def validate_endpoint(base_url: str, *, allow_remote_https: bool = False) -> str:
    parts = urlsplit(base_url.strip())
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("model endpoint must not include credentials, query or fragment")
    if parts.port is None and parts.scheme == "http":
        raise ValueError("http model endpoint must include an explicit port")
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme == "http" and loopback:
        pass
    elif parts.scheme == "https" and allow_remote_https and host:
        pass
    else:
        raise ValueError("model endpoint must be http loopback (or https when explicitly allowed)")
    return base_url.rstrip("/")


class OpenAICompatibleClient:
    """Calls ``POST {base_url}/chat/completions`` (for example the platform gateway).

    The API key is obtained from ``api_key_provider`` per request and never stored
    in this object's repr, logs or exceptions.
    """

    def __init__(
        self,
        base_url: str,
        api_key_provider: Callable[[], str] | None = None,
        model: str | None = None,
        *,
        temperature: float = 0.0,
        allow_remote_https: bool = False,
        opener: Any = None,
    ) -> None:
        self.base_url = validate_endpoint(base_url, allow_remote_https=allow_remote_https)
        self._api_key_provider = api_key_provider
        self.model = model
        self.temperature = temperature
        self._opener = opener or _DIRECT_OPENER

    def __repr__(self) -> str:
        return f"OpenAICompatibleClient(base_url={self.base_url!r}, model={self.model!r})"

    def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int, timeout: float
    ) -> ModelReply:
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": int(max_tokens),
            "stream": False,
        }
        if self.model:
            payload["model"] = self.model
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key_provider is not None:
            key = self._api_key_provider()
            if not key:
                raise ModelError("model API key is not configured")
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {429, 502, 503, 504}
            raise ModelError(f"model endpoint returned HTTP {exc.code}", retryable) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelError(f"model endpoint unreachable: {type(exc).__name__}", True) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelError("model response too large")
        return parse_chat_completion(raw)


def parse_chat_completion(raw: bytes) -> ModelReply:
    try:
        body = json.loads(raw.decode("utf-8"))
        choice = body["choices"][0]
        content = choice["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        raise ModelError("model response was not a chat completion") from None
    if not isinstance(content, str):
        raise ModelError("model response content was not text")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return ModelReply(
        content=strip_reasoning(content),
        prompt_tokens=prompt if isinstance(prompt, int) else None,
        completion_tokens=completion if isinstance(completion, int) else None,
        finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
    )


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks emitted by reasoning models such as Qwen3.x."""
    text = THINK_RE.sub("", text)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


Script = str | Callable[[list[dict[str, str]]], str] | Exception


class ScriptedModel:
    """Deterministic fake model. Each step is a string, a callable or an exception."""

    def __init__(
        self,
        steps: list[Script],
        tokens_per_reply: int = 50,
        *,
        delay_seconds: float = 0.0,
    ) -> None:
        self._steps = list(steps)
        self.calls: list[list[dict[str, str]]] = []
        self.tokens_per_reply = tokens_per_reply
        self.delay_seconds = max(0.0, float(delay_seconds))

    def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int, timeout: float
    ) -> ModelReply:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.calls.append([dict(m) for m in messages])
        if not self._steps:
            raise ModelError("scripted model has no more steps")
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        content = step(messages) if callable(step) else step
        return ModelReply(
            content=content,
            prompt_tokens=self.tokens_per_reply // 2,
            completion_tokens=self.tokens_per_reply - self.tokens_per_reply // 2,
            finish_reason="stop",
        )

    @property
    def remaining(self) -> int:
        return len(self._steps)
