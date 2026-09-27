import logging

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai import (
    AiClient,
    AiNotConfigured,
    AiUnavailable,
    get_ai_client,
)
from app.config import Settings, get_settings

# Any string works here: these tests never reach a real provider.
TEST_MODEL = "test/model"

# ---------------------------------------------------------------- route tests


class FakeClient:
    """Stands in for AiClient so route tests never touch the network."""

    def __init__(
        self,
        reply: str = "4",
        error: Exception | None = None,
        model: str = TEST_MODEL,
    ) -> None:
        self.reply = reply
        self.error = error
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply


def use_client(app: FastAPI, client: FakeClient) -> None:
    app.dependency_overrides[get_ai_client] = lambda: client


def test_ping_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/ai/ping").status_code == 401


def test_ping_returns_the_answer(app: FastAPI, signed_in: TestClient) -> None:
    use_client(app, FakeClient(reply="4"))

    response = signed_in.get("/api/ai/ping")

    assert response.status_code == 200
    assert response.json() == {"answer": "4", "model": TEST_MODEL}


def test_ping_asks_the_two_plus_two_question(
    app: FastAPI, signed_in: TestClient
) -> None:
    fake = FakeClient()
    use_client(app, fake)

    signed_in.get("/api/ai/ping")

    sent = fake.calls[0][0]["content"]
    assert "2+2" in sent


def test_ping_reports_a_missing_key_as_503(
    app: FastAPI, signed_in: TestClient
) -> None:
    use_client(app, FakeClient(error=AiNotConfigured("OPENROUTER_API_KEY is not set")))

    response = signed_in.get("/api/ai/ping")

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_ping_reports_an_upstream_failure_as_502(
    app: FastAPI, signed_in: TestClient
) -> None:
    use_client(app, FakeClient(error=AiUnavailable("upstream exploded")))

    response = signed_in.get("/api/ai/ping")

    assert response.status_code == 502
    assert "upstream exploded" in response.json()["detail"]


# ---------------------------------------------------------------- client tests


def reply_body(content: str = "4", status: int = 200) -> dict:
    return {
        "model": TEST_MODEL,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"completion_tokens": 7},
    }


def test_client_without_a_key_raises_before_any_request() -> None:
    def explode(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request should be made without a key")

    client = AiClient(api_key=None, model=TEST_MODEL, transport=httpx2.MockTransport(explode))

    with pytest.raises(AiNotConfigured):
        client.complete([{"role": "user", "content": "hi"}])


def test_client_returns_the_reply() -> None:
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=reply_body("4"))
    )
    client = AiClient(api_key="key", model=TEST_MODEL, transport=transport)

    assert client.complete([{"role": "user", "content": "2+2?"}]) == "4"


def test_client_retries_once_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx2.Response(503, json={"error": "busy"})
        return httpx2.Response(200, json=reply_body("4"))

    client = AiClient(api_key="key", model=TEST_MODEL, transport=httpx2.MockTransport(handler))

    assert client.complete([{"role": "user", "content": "2+2?"}]) == "4"
    assert calls["n"] == 2


def test_client_gives_up_after_the_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(503, json={"error": "busy"})

    client = AiClient(api_key="key", model=TEST_MODEL, transport=httpx2.MockTransport(handler))

    with pytest.raises(AiUnavailable):
        client.complete([{"role": "user", "content": "2+2?"}])
    assert calls["n"] == 2


def test_client_does_not_retry_a_rejected_key() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(401, json={"error": "bad key"})

    client = AiClient(api_key="key", model=TEST_MODEL, transport=httpx2.MockTransport(handler))

    with pytest.raises(AiUnavailable, match="OPENROUTER_API_KEY"):
        client.complete([{"role": "user", "content": "2+2?"}])
    assert calls["n"] == 1


def test_client_rejects_an_unexpected_response_shape() -> None:
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, json={"unexpected": True})
    )
    client = AiClient(api_key="key", model=TEST_MODEL, transport=transport)

    with pytest.raises(AiUnavailable):
        client.complete([{"role": "user", "content": "2+2?"}])


def test_the_api_key_is_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "sk-or-v1-super-secret-value"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=reply_body("4"))

    client = AiClient(api_key=secret, model=TEST_MODEL, transport=httpx2.MockTransport(handler))

    with caplog.at_level(logging.DEBUG):
        client.complete([{"role": "user", "content": "2+2?"}])

    assert secret not in caplog.text


def test_the_api_key_is_never_in_an_error_message() -> None:
    secret = "sk-or-v1-super-secret-value"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": "unauthorized"})

    client = AiClient(api_key=secret, model=TEST_MODEL, transport=httpx2.MockTransport(handler))

    with pytest.raises(AiUnavailable) as caught:
        client.complete([{"role": "user", "content": "2+2?"}])

    assert secret not in str(caught.value)


def test_sends_the_model_and_bearer_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx2.Response(200, json=reply_body("4"))

    client = AiClient(api_key="my-key", model=TEST_MODEL, transport=httpx2.MockTransport(handler))
    client.complete([{"role": "user", "content": "2+2?"}])

    assert seen["auth"] == "Bearer my-key"
    assert TEST_MODEL in str(seen["body"])


# ---------------------------------------------------------------- live


@pytest.mark.live
def test_the_real_model_answers(client: TestClient) -> None:
    if not get_settings().openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY is not set")

    client.post("/api/login", json={"username": "user", "password": "password"})
    response = client.get("/api/ai/ping")

    # The free tier rate-limits. That is the provider being unavailable, not a defect
    # here, so skip rather than take the suite down.
    if response.status_code == 502 and "429" in response.text:
        pytest.skip("OpenRouter is rate limiting this account")

    assert response.status_code == 200
    assert "4" in response.json()["answer"]
