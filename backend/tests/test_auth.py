from pathlib import Path

import pytest
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
    # A validly signed session, but signed with the wrong key. The context manager
    # runs the lifespan, which creates and seeds the database login now checks.
    with TestClient(
        create_app(static_dir, db_path, session_secret="secret-b")
    ) as client_b:
        client_b.post("/api/login", json={"username": "user", "password": "password"})
        cookie_from_b = client_b.cookies.get(SESSION_COOKIE)

        # Sanity: the cookie really is valid, for the app that minted it.
        assert client_b.get("/api/me").status_code == 200
        assert cookie_from_b is not None

    with TestClient(
        create_app(static_dir, db_path, session_secret="secret-a")
    ) as client_a:
        client_a.cookies.set(SESSION_COOKIE, cookie_from_b)

        assert client_a.get("/api/me").status_code == 401


def test_login_rejects_a_malformed_body(client: TestClient) -> None:
    response = client.post("/api/login", json={"username": "user"})

    assert response.status_code == 422


# ---------------------------------------------------------------- registration


def test_registration_creates_a_user_and_signs_them_in(client: TestClient) -> None:
    response = client.post(
        "/api/register", json={"username": "amir", "password": "s3cret-pw"}
    )

    assert response.status_code == 200
    assert response.json() == {"username": "amir"}
    assert SESSION_COOKIE in response.cookies
    # The session really works.
    assert client.get("/api/me").json() == {"username": "amir"}


def test_a_registered_user_can_sign_back_in(client: TestClient) -> None:
    client.post("/api/register", json={"username": "amir", "password": "s3cret-pw"})
    client.post("/api/logout")

    response = client.post(
        "/api/login", json={"username": "amir", "password": "s3cret-pw"}
    )

    assert response.status_code == 200


def test_registration_rejects_a_duplicate_username(client: TestClient) -> None:
    client.post("/api/register", json={"username": "amir", "password": "s3cret-pw"})
    client.post("/api/logout")

    response = client.post(
        "/api/register", json={"username": "amir", "password": "another-pw"}
    )

    assert response.status_code == 409
    assert SESSION_COOKIE not in response.cookies


def test_registration_cannot_take_the_demo_username(client: TestClient) -> None:
    response = client.post(
        "/api/register", json={"username": "user", "password": "another-pw"}
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", "long-enough-pw"),  # too short
        ("a" * 31, "long-enough-pw"),  # too long
        ("bad name!", "long-enough-pw"),  # bad characters
        ("", "long-enough-pw"),
        ("okname", "short"),  # password too short
        ("okname", ""),
    ],
)
def test_registration_rejects_invalid_input(
    client: TestClient, username: str, password: str
) -> None:
    response = client.post(
        "/api/register", json={"username": username, "password": password}
    )

    assert response.status_code == 422


def test_passwords_are_stored_hashed(client: TestClient, db_path: Path) -> None:
    import sqlite3

    from app.auth import verify_password

    client.post("/api/register", json={"username": "amir", "password": "s3cret-pw"})

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT password_hash FROM users WHERE username = 'amir'"
        ).fetchone()

    stored = row["password_hash"]
    assert stored.startswith("pbkdf2_sha256$")
    assert "s3cret-pw" not in stored
    assert verify_password("s3cret-pw", stored)
    assert not verify_password("wrong", stored)


def test_two_users_with_the_same_password_get_different_salts(
    client: TestClient, db_path: Path
) -> None:
    import sqlite3

    client.post("/api/register", json={"username": "amir", "password": "s3cret-pw"})
    client.post("/api/register", json={"username": "kai", "password": "s3cret-pw"})

    with sqlite3.connect(db_path) as connection:
        hashes = [
            row[0]
            for row in connection.execute(
                "SELECT password_hash FROM users WHERE username IN ('amir', 'kai')"
            )
        ]

    assert hashes[0] != hashes[1]


def test_a_registered_user_gets_a_starter_board(client: TestClient) -> None:
    client.post("/api/register", json={"username": "amir", "password": "s3cret-pw"})

    boards = client.get("/api/boards").json()

    assert len(boards) == 1
    assert boards[0]["name"] == "First board"

    board = client.get(f"/api/boards/{boards[0]['id']}/board").json()
    assert [column["title"] for column in board["columns"]] == [
        "Backlog",
        "Discovery",
        "In Progress",
        "Review",
        "Done",
    ]
    assert board["cards"] == {}
