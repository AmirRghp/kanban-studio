import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def request_raw_path(app: object, path: str) -> tuple[int, bytes]:
    """Send a path with no client-side normalisation.

    An HTTP client resolves `..` before the request leaves it, so a traversal attempt
    made through TestClient never reaches the app. Driving the ASGI callable directly
    is the only way to exercise the real path handling.
    """

    async def call() -> tuple[int, bytes]:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            sent.append(message)

        await app(scope, receive, send)  # type: ignore[operator]
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(
            m.get("body", b"") for m in sent if m["type"] == "http.response.body"
        )
        return status, body

    return asyncio.run(call())


def test_root_serves_the_index(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Kanban Studio" in response.text


def test_index_references_the_built_bundle(client: TestClient) -> None:
    response = client.get("/")

    assert "/_next/static/chunks/app.js" in response.text


def test_next_asset_is_served(client: TestClient) -> None:
    response = client.get("/_next/static/chunks/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == "console.log('app');"


def test_existing_file_is_served_instead_of_the_index(client: TestClient) -> None:
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.content == b"\x00\x00\x01\x00"


def test_unknown_path_falls_back_to_the_index(client: TestClient) -> None:
    response = client.get("/some/deep/route")

    assert response.status_code == 200
    assert "Kanban Studio" in response.text


def test_unknown_api_path_returns_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404


def test_path_traversal_does_not_escape_the_static_dir(
    static_dir: Path, db_path: Path
) -> None:
    # A real file just outside the static dir, so a successful escape is observable.
    secret = static_dir.parent / "secret.txt"
    secret.write_text("TOP_SECRET")
    app = create_app(static_dir, db_path)

    status, body = request_raw_path(app, "/../secret.txt")

    assert status == 200
    assert b"TOP_SECRET" not in body
    assert b"Kanban Studio" in body


def test_unbuilt_frontend_reports_clearly(tmp_path: Path, db_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "not-built", db_path))

    response = client.get("/")

    assert response.status_code == 503
    assert "not been built" in response.text
