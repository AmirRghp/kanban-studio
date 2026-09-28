"""Optimistic concurrency on the board and chat APIs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import RevisionConflict, load_board_with_revision, save_board, update_board

REVISION_HEADER = "X-Board-Revision"


def sign_in(client: TestClient) -> None:
    client.post("/api/login", json={"username": "user", "password": "password"})


def first_board_id(client: TestClient) -> int:
    return client.get("/api/boards").json()[0]["id"]


def board_url(client: TestClient) -> str:
    return f"/api/boards/{first_board_id(client)}/board"


def test_get_board_returns_a_revision_header(signed_in: TestClient) -> None:
    response = signed_in.get(board_url(signed_in))

    assert response.status_code == 200
    assert int(response.headers[REVISION_HEADER]) == 0


def test_put_bumps_the_revision(signed_in: TestClient) -> None:
    url = board_url(signed_in)
    first = signed_in.get(url)

    board = first.json()
    board["columns"][0]["title"] = "Renamed"
    response = signed_in.put(
        url, json=board, headers={"If-Match": first.headers[REVISION_HEADER]}
    )

    assert response.status_code == 200
    assert int(response.headers[REVISION_HEADER]) == 1
    assert signed_in.get(url).headers[REVISION_HEADER] == "1"


def test_put_with_a_stale_revision_conflicts(signed_in: TestClient) -> None:
    url = board_url(signed_in)
    stale = signed_in.get(url).headers[REVISION_HEADER]

    # Someone else writes between our read and our write.
    board = signed_in.get(url).json()
    board["columns"][0]["title"] = "Other writer"
    signed_in.put(url, json=board)

    board = signed_in.get(url).json()
    board["columns"][0]["title"] = "My stale write"
    response = signed_in.put(url, json=board, headers={"If-Match": stale})

    assert response.status_code == 409
    # The other writer's change survived; ours did not land.
    titles = [c["title"] for c in signed_in.get(url).json()["columns"]]
    assert "Other writer" in titles
    assert "My stale write" not in titles


def test_put_without_if_match_still_writes(signed_in: TestClient) -> None:
    url = board_url(signed_in)
    before = signed_in.get(url).headers[REVISION_HEADER]

    board = signed_in.get(url).json()
    board["columns"][0]["title"] = "No header"
    response = signed_in.put(url, json=board)

    assert response.status_code == 200
    assert int(response.headers[REVISION_HEADER]) == int(before) + 1


def test_chat_response_carries_the_new_revision(
    app, signed_in: TestClient
) -> None:  # type: ignore[no-untyped-def]
    class FakeAi:
        model = "test/model"

        def complete_json(self, messages, schema, name):  # type: ignore[no-untyped-def]
            return {"reply": "ok", "operations": []}

    from app.ai import get_ai_client

    app.dependency_overrides[get_ai_client] = lambda: FakeAi()
    before = int(signed_in.get(board_url(signed_in)).headers[REVISION_HEADER])

    response = signed_in.post(
        "/api/chat",
        json={"message": "hi", "history": [], "board_id": first_board_id(signed_in)},
    )

    assert response.status_code == 200
    assert int(response.headers[REVISION_HEADER]) == before + 1
    app.dependency_overrides.pop(get_ai_client, None)


def test_chat_with_a_stale_revision_conflicts(app, signed_in: TestClient) -> None:  # type: ignore[no-untyped-def]
    class FakeAi:
        model = "test/model"

        def complete_json(self, messages, schema, name):  # type: ignore[no-untyped-def]
            return {
                "reply": "ok",
                "operations": [
                    {"op": "rename_column", "column_id": "col-backlog", "title": "X"}
                ],
            }

    from app.ai import get_ai_client

    app.dependency_overrides[get_ai_client] = lambda: FakeAi()
    url = board_url(signed_in)
    stale = signed_in.get(url).headers[REVISION_HEADER]

    # Another writer lands between our snapshot and the model's reply.
    board = signed_in.get(url).json()
    board["columns"][0]["title"] = "Other writer"
    signed_in.put(url, json=board)

    response = signed_in.post(
        "/api/chat",
        json={"message": "hi", "history": [], "board_id": first_board_id(signed_in)},
        headers={"If-Match": stale},
    )

    assert response.status_code == 409
    titles = [c["title"] for c in signed_in.get(url).json()["columns"]]
    assert "Other writer" in titles
    assert "X" not in titles
    app.dependency_overrides.pop(get_ai_client, None)


# ------------------------------------------------------------ database layer


def test_save_board_refuses_a_stale_revision(db_path: Path) -> None:
    from app.db import initialise

    initialise(db_path)
    board = load_board_with_revision(db_path, "user", 1)
    assert board is not None

    # A concurrent writer bumps the revision.
    concurrent = load_board_with_revision(db_path, "user", 1)
    assert concurrent is not None
    save_board(db_path, "user", 1, concurrent[0], expected_revision=concurrent[1])

    with pytest.raises(RevisionConflict):
        save_board(db_path, "user", 1, board[0], expected_revision=board[1])


def test_update_board_returns_the_new_revision(db_path: Path) -> None:
    from app.db import initialise

    initialise(db_path)
    _, revision = update_board(
        db_path, "user", 1, lambda b: b.model_copy(deep=True), expected_revision=0
    )

    assert revision == 1
    reloaded = load_board_with_revision(db_path, "user", 1)
    assert reloaded is not None
    assert reloaded[1] == 1


def test_update_board_detects_a_concurrent_change(db_path: Path) -> None:
    from app.db import initialise

    initialise(db_path)
    # Read, then let another writer bump the revision, then apply with the stale one.
    update_board(db_path, "user", 1, lambda b: b.model_copy(deep=True))

    with pytest.raises(RevisionConflict):
        update_board(
            db_path, "user", 1, lambda b: b.model_copy(deep=True), expected_revision=0
        )
