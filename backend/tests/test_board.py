import json
import sqlite3
from base64 import b64encode
from pathlib import Path

import itsdangerous
from fastapi.testclient import TestClient

from app.db import SEED_BOARD, initialise, load_board, save_board
from app.models import BoardData
from conftest import TEST_SESSION_SECRET

SESSION_COOKIE = "session"


def sign_in(client: TestClient) -> None:
    client.post("/api/login", json={"username": "user", "password": "password"})


def cookie_for(username: str) -> str:
    """Mint a session cookie for any user, to prove boards are isolated per user.

    Mirrors how SessionMiddleware encodes the payload, so it deliberately couples to
    Starlette's cookie format.
    """
    payload = b64encode(json.dumps({"username": username}).encode("utf-8"))
    return itsdangerous.TimestampSigner(TEST_SESSION_SECRET).sign(payload).decode()


def add_user_with_board(db_path: Path, username: str, title: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO users (username) VALUES (?)", (username,))
        user_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()[0]
        board = BoardData.model_validate(
            {
                "columns": [{"id": "only", "title": title, "cardIds": []}],
                "cards": {},
            }
        )
        connection.execute(
            "INSERT INTO boards (user_id, data) VALUES (?, ?)",
            (user_id, board.model_dump_json()),
        )


def test_board_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/board").status_code == 401


def test_put_board_requires_a_session(client: TestClient) -> None:
    response = client.put("/api/board", json=SEED_BOARD.model_dump())

    assert response.status_code == 401


def test_first_run_seeds_a_five_column_board(client: TestClient) -> None:
    sign_in(client)

    board = client.get("/api/board").json()

    assert len(board["columns"]) == 5
    assert len(board["cards"]) == 8
    assert [column["title"] for column in board["columns"]] == [
        "Backlog",
        "Discovery",
        "In Progress",
        "Review",
        "Done",
    ]


def test_board_round_trips_through_a_write(client: TestClient) -> None:
    sign_in(client)
    original = client.get("/api/board").json()

    original["columns"][0]["title"] = "Renamed"
    original["columns"][0]["cardIds"] = ["card-2", "card-1"]
    original["cards"]["card-1"]["title"] = "Edited title"
    del original["cards"]["card-8"]
    original["columns"][4]["cardIds"] = ["card-7"]

    assert client.put("/api/board", json=original).status_code == 200
    assert client.get("/api/board").json() == original


def test_put_rejects_a_dangling_card_reference(client: TestClient) -> None:
    sign_in(client)
    before = client.get("/api/board").json()

    broken = client.get("/api/board").json()
    broken["columns"][0]["cardIds"].append("card-does-not-exist")

    assert client.put("/api/board", json=broken).status_code == 422
    assert client.get("/api/board").json() == before


def test_put_rejects_a_malformed_body(client: TestClient) -> None:
    sign_in(client)

    assert client.put("/api/board", json={"columns": []}).status_code == 422
    assert client.put("/api/board", json="not an object").status_code == 422


def test_put_does_not_leak_across_users(client: TestClient, db_path: Path) -> None:
    add_user_with_board(db_path, "other", "Other Board")
    sign_in(client)
    mine = client.get("/api/board").json()

    theirs = TestClient(client.app)
    theirs.cookies.set(SESSION_COOKIE, cookie_for("other"))
    assert theirs.get("/api/board").json()["columns"][0]["title"] == "Other Board"

    mine["columns"][0]["title"] = "Mine Only"
    client.put("/api/board", json=mine)

    # The other user's board is untouched by our write.
    assert theirs.get("/api/board").json()["columns"][0]["title"] == "Other Board"


def test_a_missing_user_has_no_board(client: TestClient) -> None:
    sign_in(client)
    client.cookies.set(SESSION_COOKIE, cookie_for("ghost"))

    assert client.get("/api/board").status_code == 404


def test_database_is_recreated_and_reseeded_when_deleted(
    client: TestClient, db_path: Path
) -> None:
    sign_in(client)
    edited = client.get("/api/board").json()
    edited["columns"][0]["title"] = "Changed"
    client.put("/api/board", json=edited)
    assert db_path.is_file()

    db_path.unlink()

    initialise(db_path)
    assert db_path.is_file()
    assert load_board(db_path, "user").columns[0].title == "Backlog"


def test_initialise_is_idempotent(db_path: Path) -> None:
    initialise(db_path)
    initialise(db_path)

    with sqlite3.connect(db_path) as connection:
        users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        boards = connection.execute("SELECT COUNT(*) FROM boards").fetchone()[0]

    assert (users, boards) == (1, 1)


def test_seed_board_matches_the_frontend_initial_data() -> None:
    # Guards the duplication noted in db.py: the backend seed and the frontend's
    # initialData must not drift apart.
    from test_models import FRONTEND_BOARD

    assert SEED_BOARD.model_dump() == FRONTEND_BOARD


def test_save_and_load_at_the_database_layer(db_path: Path) -> None:
    initialise(db_path)
    board = load_board(db_path, "user")
    assert board is not None

    board.columns[0].title = "Renamed In Place"
    save_board(db_path, "user", board)

    assert load_board(db_path, "user").columns[0].title == "Renamed In Place"


def test_a_legacy_database_without_revision_is_migrated(db_path: Path) -> None:
    import sqlite3

    from app.db import load_board_with_revision

    # Create the pre-revision schema by hand, exactly as an older build left it.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id       INTEGER PRIMARY KEY,
                username TEXT    NOT NULL UNIQUE
            );
            CREATE TABLE boards (
                id      INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                data    TEXT    NOT NULL
            );
            """
        )

    initialise(db_path)

    loaded = load_board_with_revision(db_path, "user")
    assert loaded is not None
    board, revision = loaded
    assert revision == 0
    assert board.columns[0].title == "Backlog"
