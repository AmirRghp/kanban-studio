from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_insecure_default_secret_logs_a_warning(
    static_dir, db_path, caplog  # type: ignore[no-untyped-def]
) -> None:
    import logging

    from app.main import create_app

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app(static_dir, db_path)) as client:
            client.get("/api/health")

    assert any("SESSION_SECRET" in record.message for record in caplog.records)


def test_a_custom_secret_does_not_warn(
    static_dir, db_path, caplog  # type: ignore[no-untyped-def]
) -> None:
    import logging

    from app.main import create_app

    with caplog.at_level(logging.WARNING):
        with TestClient(
            create_app(static_dir, db_path, session_secret="a-real-secret")
        ) as client:
            client.get("/api/health")

    assert not any("SESSION_SECRET" in record.message for record in caplog.records)
