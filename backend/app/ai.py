import json
import logging
import time
from typing import Annotated, Any, Literal

import httpx2
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 30.0
# The model is free tier, so it can be busy or briefly unavailable. One retry, no more,
# so a genuine outage fails fast instead of hanging a request.
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.0

PING_PROMPT = "What is 2+2? Reply with just the number."


class ChatMessage(BaseModel):
    """One transcript entry from the client. Roles are closed: a client that can
    inject a `system` message into the middle of the history could contradict the
    system rules, so anything else is rejected as 422."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """One turn of conversation. The transcript is never stored server-side."""

    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class AiError(Exception):
    """Base class so routes can map failures to status codes."""


class AiNotConfigured(AiError):
    """No API key is configured."""


class AiUnavailable(AiError):
    """The upstream call failed, timed out, or returned something unusable."""


class AiClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        # One client for the process: openrouter.ai is the only upstream, and reusing
        # the client reuses its connection pool instead of a TLS handshake per call.
        # The transport parameter keeps tests hermetic.
        self._client = httpx2.Client(timeout=TIMEOUT_SECONDS, transport=transport)

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the assistant's reply text.

        Raises AiNotConfigured if there is no key, AiUnavailable if the call fails.
        """
        return self._run(messages)

    def complete_json(
        self, messages: list[dict[str, str]], schema: dict[str, Any], name: str
    ) -> dict[str, Any]:
        """Return the assistant's reply parsed as JSON matching `schema`."""
        text = self._run(messages, schema=schema, name=name)
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise AiUnavailable(f"reply was not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AiUnavailable("reply was JSON but not an object")
        return parsed

    def _run(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        name: str = "response",
    ) -> str:
        if not self._api_key:
            raise AiNotConfigured("OPENROUTER_API_KEY is not set")

        last_error = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._attempt(messages, schema, name)
            except _Retryable as exc:
                last_error = str(exc)
                logger.warning(
                    "OpenRouter attempt %d/%d failed: %s",
                    attempt,
                    MAX_ATTEMPTS,
                    last_error,
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS)

        raise AiUnavailable(f"OpenRouter request failed: {last_error}")

    def _attempt(
        self, messages: list[dict[str, str]], schema: dict[str, Any] | None, name: str
    ) -> str:
        response = self._client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=self._body(messages, schema, name, self.model),
        )

        # A bad key or a malformed request will not fix itself, so do not retry it.
        if response.status_code in (401, 403):
            raise AiUnavailable(
                f"OpenRouter rejected the request ({response.status_code}). "
                "Check OPENROUTER_API_KEY."
            )

        if response.status_code >= 400:
            raise _Retryable(f"HTTP {response.status_code}")

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise _Retryable(f"unexpected response shape: {exc}") from exc

        # Never log the key, only the shape of what came back.
        logger.info(
            "OpenRouter reply from %s: %s completion tokens",
            payload.get("model", self.model),
            payload.get("usage", {}).get("completion_tokens"),
        )
        return str(content)

    @staticmethod
    def _body(
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None,
        name: str,
        model: str,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "messages": messages}
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            }
        return body


class _Retryable(Exception):
    """Internal marker for failures worth one more attempt."""


def get_ai_client() -> AiClient:
    settings = get_settings()
    return AiClient(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
