from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

SESSION_COOKIE = "session"


def test_login_with_correct_credentials_sets_a_session(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/login", json={"username": "user", "password": "password"}
    )

    assert response.status_code == 200
    assert response.json() == {"username": "user"}
    assert SESSION_COOKIE in response.cookies


def test_login_sets_an_httponly_cookie(client: TestClient) -> None:
    response = client.post(
        "/api/login", json={"username": "user", "password": "password"}
    )

    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


def test_login_with_a_wrong_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/login", json={"username": "user", "password": "nope"}
    )

    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_login_with_a_wrong_username_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/login", json={"username": "someone", "password": "password"}
    )

    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_me_returns_the_username_when_signed_in(client: TestClient) -> None:
    client.post("/api/login", json={"username": "user", "password": "password"})

    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json() == {"username": "user"}


def test_me_returns_401_without_a_session(client: TestClient) -> None:
    response = client.get("/api/me")

    assert response.status_code == 401


def test_logout_clears_the_session(client: TestClient) -> None:
    client.post("/api/login", json={"username": "user", "password": "password"})

    response = client.post("/api/logout")

    assert response.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_a_forged_session_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "user")

    response = client.get("/api/me")

    assert response.status_code == 401


def test_a_session_signed_with_another_secret_is_rejected(
    static_dir: Path, db_path: Path
) -> None:
    # A validly signed session, but signed with the wrong key.
    client_b = TestClient(create_app(static_dir, db_path, session_secret="secret-b"))
    client_b.post("/api/login", json={"username": "user", "password": "password"})
    cookie_from_b = client_b.cookies.get(SESSION_COOKIE)

    # Sanity: the cookie really is valid, for the app that minted it.
    assert client_b.get("/api/me").status_code == 200
    assert cookie_from_b is not None

    client_a = TestClient(create_app(static_dir, db_path, session_secret="secret-a"))
    client_a.cookies.set(SESSION_COOKIE, cookie_from_b)

    assert client_a.get("/api/me").status_code == 401


def test_login_rejects_a_malformed_body(client: TestClient) -> None:
    response = client.post("/api/login", json={"username": "user"})

    assert response.status_code == 422
