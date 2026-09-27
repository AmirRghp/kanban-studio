"""OPENROUTER_MODEL must actually reach the outgoing request."""

import json

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai import AiClient, get_ai_client
from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    # get_settings is cached, so an env change would otherwise be invisible.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_default_to_a_working_model() -> None:
    assert Settings().openrouter_model


def test_settings_read_the_model_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "some-vendor/some-model:free")

    assert Settings().openrouter_model == "some-vendor/some-model:free"


def test_settings_fall_back_to_the_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    assert Settings().openrouter_model == "dots-studio/dots-3-note-preview:free"


def test_get_ai_client_uses_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "chosen/model:free")

    assert get_ai_client().model == "chosen/model:free"


def test_the_configured_model_is_what_gets_sent() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = request.read().decode()
        return httpx2.Response(
            200,
            json={
                "model": "chosen/model:free",
                "choices": [{"message": {"role": "assistant", "content": "4"}}],
                "usage": {"completion_tokens": 1},
            },
        )

    client = AiClient(
        api_key="key",
        model="chosen/model:free",
        transport=httpx2.MockTransport(handler),
    )
    client.complete([{"role": "user", "content": "2+2?"}])

    assert json.loads(str(seen["body"]))["model"] == "chosen/model:free"


def test_the_configured_model_is_used_for_structured_output() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = request.read().decode()
        return httpx2.Response(
            200,
            json={"choices": [{"message": {"content": '{"reply":"x","operations":[]}'}}]},
        )

    client = AiClient(
        api_key="key",
        model="structured/model:free",
        transport=httpx2.MockTransport(handler),
    )
    client.complete_json([{"role": "user", "content": "hi"}], {}, "r")

    assert json.loads(str(seen["body"]))["model"] == "structured/model:free"


def test_the_ping_route_reports_the_model_in_use(
    app: FastAPI, signed_in: TestClient
) -> None:
    class Reporting:
        model = "reported/model:free"

        def complete(self, messages: list[dict]) -> str:
            return "4"

    app.dependency_overrides[get_ai_client] = lambda: Reporting()

    response = signed_in.get("/api/ai/ping")

    assert response.json()["model"] == "reported/model:free"


def test_a_real_client_built_from_the_environment_has_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "env/model:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")

    client = get_ai_client()

    assert client.model == "env/model:free"
    assert isinstance(client, AiClient)
