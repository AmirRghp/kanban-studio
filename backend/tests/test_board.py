import json
import sqlite3
from base64 import b64encode
from pathlib import Path

import itsdangerous
from fastapi.testclient import TestClient

from app.db import SEED_BOARD, initialise, save_board
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
        connection.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, 'x')", (username,)
        )
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
            "INSERT INTO boards (user_id, name, data) VALUES (?, 'Their board', ?)",
            (user_id, board.model_dump_json()),
        )


def board_url(client: TestClient) -> str:
    board_id = client.get("/api/boards").json()[0]["id"]
    return f"/api/boards/{board_id}/board"


# ---------------------------------------------------------------- the board data


def test_board_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/boards").status_code == 401
    assert client.get("/api/boards/1/board").status_code == 401
    assert client.put("/api/boards/1/board", json=SEED_BOARD.model_dump()).status_code == 401


def test_first_run_seeds_a_five_column_board(client: TestClient) -> None:
    sign_in(client)

    board = client.get(board_url(client)).json()

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
    url = board_url(client)
    original = client.get(url).json()

    original["columns"][0]["title"] = "Renamed"
    original["columns"][0]["cardIds"] = ["card-2", "card-1"]
    original["cards"]["card-1"]["title"] = "Edited title"
    del original["cards"]["card-8"]
    original["columns"][4]["cardIds"] = ["card-7"]

    assert client.put(url, json=original).status_code == 200
    assert client.get(url).json() == original


def test_put_rejects_a_dangling_card_reference(client: TestClient) -> None:
    sign_in(client)
    url = board_url(client)
    before = client.get(url).json()

    broken = client.get(url).json()
    broken["columns"][0]["cardIds"].append("card-does-not-exist")

    assert client.put(url, json=broken).status_code == 422
    assert client.get(url).json() == before


def test_put_rejects_a_malformed_body(client: TestClient) -> None:
    sign_in(client)

    assert client.put(board_url(client), json={"columns": []}).status_code == 422
    assert client.put(board_url(client), json="not an object").status_code == 422


def test_a_missing_board_returns_404(client: TestClient) -> None:
    sign_in(client)

    assert client.get("/api/boards/999/board").status_code == 404
    assert client.put("/api/boards/999/board", json=SEED_BOARD.model_dump()).status_code == 404


def test_another_users_board_is_invisible(client: TestClient, db_path: Path) -> None:
    add_user_with_board(db_path, "other", "Other Board")
    sign_in(client)

    theirs = TestClient(client.app)
    theirs.cookies.set(SESSION_COOKIE, cookie_for("other"))

    # Neither user can reach the other's board by id.
    their_id = theirs.get("/api/boards").json()[0]["id"]
    my_ids = [b["id"] for b in client.get("/api/boards").json()]
    assert their_id not in my_ids
    assert client.get(f"/api/boards/{their_id}/board").status_code == 404


def test_board_writes_do_not_leak_across_users(client: TestClient, db_path: Path) -> None:
    add_user_with_board(db_path, "other", "Other Board")
    sign_in(client)
    mine = client.get(board_url(client)).json()

    theirs = TestClient(client.app)
    theirs.cookies.set(SESSION_COOKIE, cookie_for("other"))
    their_url = f"/api/boards/{theirs.get('/api/boards').json()[0]['id']}/board"
    assert theirs.get(their_url).json()["columns"][0]["title"] == "Other Board"

    mine["columns"][0]["title"] = "Mine Only"
    client.put(board_url(client), json=mine)

    # The other user's board is untouched by our write.
    assert theirs.get(their_url).json()["columns"][0]["title"] == "Other Board"


def test_a_missing_user_has_no_boards(client: TestClient) -> None:
    sign_in(client)
    client.cookies.set(SESSION_COOKIE, cookie_for("ghost"))

    assert client.get("/api/boards").json() == []
    assert client.get("/api/boards/1/board").status_code == 404


# ---------------------------------------------------------------- board CRUD


def test_a_user_can_create_and_list_boards(client: TestClient) -> None:
    sign_in(client)

    created = client.post("/api/boards", json={"name": "Side project"})
    assert created.status_code == 201
    assert created.json()["name"] == "Side project"

    boards = client.get("/api/boards").json()
    assert [board["name"] for board in boards] == ["First board", "Side project"]
    assert boards[0]["cardCount"] == 8
    assert boards[1]["cardCount"] == 0


def test_a_created_board_is_empty_with_five_columns(client: TestClient) -> None:
    sign_in(client)
    board_id = client.post("/api/boards", json={"name": "New"}).json()["id"]

    board = client.get(f"/api/boards/{board_id}/board").json()

    assert [column["title"] for column in board["columns"]] == [
        "Backlog",
        "Discovery",
        "In Progress",
        "Review",
        "Done",
    ]
    assert board["cards"] == {}


def test_a_board_can_be_renamed(client: TestClient) -> None:
    sign_in(client)
    board_id = client.get("/api/boards").json()[0]["id"]

    response = client.put(f"/api/boards/{board_id}", json={"name": "Renamed board"})

    assert response.status_code == 200
    assert client.get("/api/boards").json()[0]["name"] == "Renamed board"


def test_a_board_rename_to_an_empty_name_is_rejected(client: TestClient) -> None:
    sign_in(client)
    board_id = client.get("/api/boards").json()[0]["id"]

    assert client.put(f"/api/boards/{board_id}", json={"name": "  "}).status_code == 422


def test_a_board_can_be_deleted(client: TestClient) -> None:
    sign_in(client)
    board_id = client.post("/api/boards", json={"name": "Doomed"}).json()["id"]

    assert client.delete(f"/api/boards/{board_id}").status_code == 200
    assert client.get(f"/api/boards/{board_id}/board").status_code == 404
    assert [b["name"] for b in client.get("/api/boards").json()] == ["First board"]


def test_deleting_another_users_board_is_refused(
    client: TestClient, db_path: Path
) -> None:
    add_user_with_board(db_path, "other", "Other Board")
    sign_in(client)

    theirs = TestClient(client.app)
    theirs.cookies.set(SESSION_COOKIE, cookie_for("other"))
    their_id = theirs.get("/api/boards").json()[0]["id"]

    assert client.delete(f"/api/boards/{their_id}").status_code == 404
    assert theirs.get(f"/api/boards/{their_id}/board").status_code == 200


# ---------------------------------------------------------------- legacy aliases


def test_the_legacy_board_route_still_serves_the_first_board(
    client: TestClient,
) -> None:
    sign_in(client)

    legacy = client.get("/api/board")
    scoped = client.get(board_url(client))

    assert legacy.status_code == 200
    assert legacy.json() == scoped.json()
    assert legacy.headers["X-Board-Revision"] == scoped.headers["X-Board-Revision"]


def test_the_legacy_put_route_writes_the_first_board(client: TestClient) -> None:
    sign_in(client)
    board = client.get("/api/board").json()
    board["columns"][0]["title"] = "Via Legacy"

    assert client.put("/api/board", json=board).status_code == 200
    assert client.get(board_url(client)).json()["columns"][0]["title"] == "Via Legacy"


# ---------------------------------------------------------------- database layer


def test_database_is_recreated_and_reseeded_when_deleted(
    client: TestClient, db_path: Path
) -> None:
    sign_in(client)
    edited = client.get(board_url(client)).json()
    edited["columns"][0]["title"] = "Changed"
    client.put(board_url(client), json=edited)
    assert db_path.is_file()

    db_path.unlink()

    initialise(db_path)
    assert db_path.is_file()
    row = sqlite3.connect(db_path).execute(
        "SELECT data FROM boards WHERE user_id = (SELECT id FROM users WHERE username = 'user')"
    ).fetchone()
    assert BoardData.model_validate_json(row[0]).columns[0].title == "Backlog"


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
    from test_models import FRONTEND_BOARD, _without_optional_fields

    assert _without_optional_fields(SEED_BOARD.model_dump()) == FRONTEND_BOARD


def test_save_and_load_at_the_database_layer(db_path: Path) -> None:
    initialise(db_path)
    board = BoardData.model_validate(
        {
            "columns": [{"id": "only", "title": "Renamed In Place", "cardIds": []}],
            "cards": {},
        }
    )
    save_board(db_path, "user", 1, board)

    reloaded = client_level_load(db_path)
    assert reloaded is not None and reloaded[0].columns[0].title == "Renamed In Place"


def client_level_load(db_path: Path):
    from app.db import load_board_with_revision

    return load_board_with_revision(db_path, "user", 1)


def test_an_old_database_is_migrated_keeping_data_and_revision(
    db_path: Path,
) -> None:
    # Create the pre-Part-11 schema by hand, exactly as an older build left it: no
    # password_hash, no board name, UNIQUE(user_id), and a revision column.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            f"""
            CREATE TABLE users (
                id       INTEGER PRIMARY KEY,
                username TEXT    NOT NULL UNIQUE
            );
            CREATE TABLE boards (
                id       INTEGER PRIMARY KEY,
                user_id  INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                data     TEXT    NOT NULL,
                revision INTEGER NOT NULL DEFAULT 3
            );
            INSERT INTO users (username) VALUES ('user');
            INSERT INTO boards (user_id, data, revision)
            VALUES (1, '{SEED_BOARD.model_dump_json()}', 3);
            """
        )

    initialise(db_path)

    from app.db import check_credentials, load_board_with_revision

    # The demo user's credentials were backfilled from the hardcoded default.
    assert check_credentials(db_path, "user", "password")
    assert not check_credentials(db_path, "user", "wrong")

    loaded = load_board_with_revision(db_path, "user", 1)
    assert loaded is not None
    board, revision = loaded
    # Data and revision both carried across the rebuild.
    assert revision == 3
    assert board.columns[0].title == "Backlog"
    assert board.cards["card-1"].title == "Align roadmap themes"

    # The new shape really is in place: a second board for the same user is allowed.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO boards (user_id, name, data) VALUES (1, 'Second', ?)",
            (SEED_BOARD.model_dump_json(),),
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM boards WHERE user_id = 1"
        ).fetchone()[0]
    assert count == 2
