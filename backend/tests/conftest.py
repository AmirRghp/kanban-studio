import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app

TEST_SESSION_SECRET = "test-secret"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip tests marked `live` unless RUN_LIVE=1, so the default run never
    touches the network or spends tokens."""
    if os.environ.get("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE=1 to run live API tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A stand-in for the built frontend, so routing can be tested without a build."""
    out = tmp_path / "out"
    (out / "_next" / "static" / "chunks").mkdir(parents=True)
    (out / "index.html").write_text(
        "<!doctype html><html><body><h1>Kanban Studio</h1>"
        '<script src="/_next/static/chunks/app.js"></script></body></html>'
    )
    (out / "_next" / "static" / "chunks" / "app.js").write_text("console.log('app');")
    (out / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    return out


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A database that does not exist yet, so every test exercises first-run setup."""
    return tmp_path / "data" / "app.db"


@pytest.fixture
def app(static_dir: Path, db_path: Path) -> FastAPI:
    return create_app(static_dir, db_path, session_secret=TEST_SESSION_SECRET)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager runs the lifespan, which creates and seeds the database.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    client.post("/api/login", json={"username": "user", "password": "password"})
    return client
