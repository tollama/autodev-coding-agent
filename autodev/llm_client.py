from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import httpx


class LLMTokenBudgetExceeded(RuntimeError):
    """Raised when cumulative token usage crosses configured budget."""


class LLMClient:
    """OpenAI-compatible Chat Completions client with retry and token budgeting."""

    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    RETRY_BACKOFF_SECONDS = (2, 4, 8)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_sec: int = 240,
        *,
        max_total_tokens: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout_sec
        self.max_total_tokens = max_total_tokens

        self._usage_totals: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._chat_calls = 0
        self._failed_chat_calls = 0
        self._transport_retries = 0

    @staticmethod
    def _coerce_usage_int(value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float) and value.is_integer():
            return max(0, int(value))
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return 0
            try:
                return max(0, int(stripped))
            except ValueError:
                return 0
        return 0

    @classmethod
    def _is_retryable_status(cls, status_code: int) -> bool:
        return status_code in cls.RETRYABLE_STATUS_CODES

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else 0
            return LLMClient._is_retryable_status(status)
        return False

    def _update_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self._usage_totals[key] += self._coerce_usage_int(usage.get(key))

        if self.max_total_tokens is not None and self._usage_totals["total_tokens"] > self.max_total_tokens:
            raise LLMTokenBudgetExceeded(
                "LLM token budget exceeded: "
                f"used={self._usage_totals['total_tokens']} max={self.max_total_tokens}"
            )

    def usage_summary(self) -> Dict[str, int | None]:
        remaining = None
        if self.max_total_tokens is not None:
            remaining = max(0, self.max_total_tokens - self._usage_totals["total_tokens"])
        return {
            **self._usage_totals,
            "max_total_tokens": self.max_total_tokens,
            "remaining_tokens": remaining,
            "chat_calls": self._chat_calls,
            "failed_chat_calls": self._failed_chat_calls,
            "transport_retries": self._transport_retries,
        }

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        self._chat_calls += 1
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        max_retries = len(self.RETRY_BACKOFF_SECONDS)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    self._update_usage(data.get("usage"))
                    content = data["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("LLM response content must be a string.")
                    return content
                except Exception as exc:
                    if not self._is_retryable_error(exc) or attempt >= max_retries:
                        self._failed_chat_calls += 1
                        raise
                    self._transport_retries += 1
                    await asyncio.sleep(self.RETRY_BACKOFF_SECONDS[attempt])

        self._failed_chat_calls += 1
        raise RuntimeError("LLM request failed without a terminal exception.")
