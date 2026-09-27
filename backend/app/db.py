import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from app.auth import VALID_USERNAME
from app.models import BoardData

# Mirrors docs/DATA-MODEL.md. IF NOT EXISTS keeps startup idempotent.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY,
    username TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS boards (
    id       INTEGER PRIMARY KEY,
    user_id  INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    data     TEXT    NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
"""

# Boards created before the revision column existed. Every entry is guarded by a pragma
# check, so running initialise repeatedly is still safe.
_MIGRATIONS = (
    "ALTER TABLE boards ADD COLUMN revision INTEGER NOT NULL DEFAULT 0",
)

# One busy timeout in one place. Two writers both doing read-modify-write inside
# update_board will serialize here instead of throwing 'database is locked'.
_BUSY_TIMEOUT_SECONDS = 5.0


def _add_revision_column_if_missing(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(boards)").fetchall()
    }
    if "revision" in columns:
        return
    for statement in _MIGRATIONS:
        if "ADD COLUMN revision" in statement:
            connection.execute(statement)


# The same board the frontend ships as `initialData`, so a fresh database looks like the
# demo the user has already seen. It is duplicated rather than shared because the
# frontend's copy is TypeScript inside a separate build. `test_board.py` asserts the two
# stay identical, so drift fails the suite instead of reaching production.
SEED_BOARD = BoardData.model_validate(
    {
        "columns": [
            {"id": "col-backlog", "title": "Backlog", "cardIds": ["card-1", "card-2"]},
            {"id": "col-discovery", "title": "Discovery", "cardIds": ["card-3"]},
            {
                "id": "col-progress",
                "title": "In Progress",
                "cardIds": ["card-4", "card-5"],
            },
            {"id": "col-review", "title": "Review", "cardIds": ["card-6"]},
            {"id": "col-done", "title": "Done", "cardIds": ["card-7", "card-8"]},
        ],
        "cards": {
            "card-1": {
                "id": "card-1",
                "title": "Align roadmap themes",
                "details": "Draft quarterly themes with impact statements and metrics.",
            },
            "card-2": {
                "id": "card-2",
                "title": "Gather customer signals",
                "details": "Review support tags, sales notes, and churn feedback.",
            },
            "card-3": {
                "id": "card-3",
                "title": "Prototype analytics view",
                "details": "Sketch initial dashboard layout and key drill-downs.",
            },
            "card-4": {
                "id": "card-4",
                "title": "Refine status language",
                "details": "Standardize column labels and tone across the board.",
            },
            "card-5": {
                "id": "card-5",
                "title": "Design card layout",
                "details": "Add hierarchy and spacing for scanning dense lists.",
            },
            "card-6": {
                "id": "card-6",
                "title": "QA micro-interactions",
                "details": "Verify hover, focus, and loading states.",
            },
            "card-7": {
                "id": "card-7",
                "title": "Ship marketing page",
                "details": "Final copy approved and asset pack delivered.",
            },
            "card-8": {
                "id": "card-8",
                "title": "Close onboarding sprint",
                "details": "Document release notes and share internally.",
            },
        },
    }
)


@contextmanager
def _connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialise(db_path: Path) -> None:
    """Create the database and schema if absent, then seed the demo user and board."""
    with _connection(db_path) as connection:
        connection.executescript(SCHEMA)
        _add_revision_column_if_missing(connection)
        connection.execute(
            "INSERT OR IGNORE INTO users (username) VALUES (?)", (VALID_USERNAME,)
        )
        user_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", (VALID_USERNAME,)
        ).fetchone()["id"]
        has_board = connection.execute(
            "SELECT 1 FROM boards WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not has_board:
            connection.execute(
                "INSERT INTO boards (user_id, data) VALUES (?, ?)",
                (user_id, SEED_BOARD.model_dump_json()),
            )


def load_board(db_path: Path, username: str) -> BoardData | None:
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT boards.data AS data FROM boards "
            "JOIN users ON users.id = boards.user_id "
            "WHERE users.username = ?",
            (username,),
        ).fetchone()
    return BoardData.model_validate_json(row["data"]) if row else None


def load_board_with_revision(db_path: Path, username: str) -> tuple[BoardData, int] | None:
    """The board plus its current revision, for optimistic concurrency on the API."""
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT boards.data AS data, boards.revision AS revision "
            "FROM boards "
            "JOIN users ON users.id = boards.user_id "
            "WHERE users.username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return BoardData.model_validate_json(row["data"]), row["revision"]


class RevisionConflict(Exception):
    """Another writer changed the board between our read and our write."""


def update_board(
    db_path: Path,
    username: str,
    change: Callable[[BoardData], BoardData],
    expected_revision: int | None = None,
) -> tuple[BoardData, int]:
    """Read, transform, and write in one transaction, returning the new revision.

    The chat path uses this so a conversation cannot clobber a board change made
    between its own read and write. With expected_revision set, a change made after
    the caller's read raises RevisionConflict instead of being applied on top of it.
    """
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT boards.data AS data, boards.revision AS revision "
            "FROM boards "
            "JOIN users ON users.id = boards.user_id "
            "WHERE users.username = ?",
            (username,),
        ).fetchone()
        if row is None:
            raise LookupError(f"no board for user {username!r}")

        if expected_revision is not None and row["revision"] != expected_revision:
            raise RevisionConflict(
                f"board changed since read (expected revision {expected_revision}, "
                f"current is {row['revision']})"
            )

        updated = change(BoardData.model_validate_json(row["data"]))
        new_revision = row["revision"] + 1
        connection.execute(
            "UPDATE boards SET data = ?, revision = ? "
            "WHERE user_id = (SELECT id FROM users WHERE username = ?)",
            (updated.model_dump_json(), new_revision, username),
        )
        return updated, new_revision


def save_board(
    db_path: Path,
    username: str,
    board: BoardData,
    expected_revision: int | None = None,
) -> None:
    """Replace the stored board, bumping the revision.

    With expected_revision set, the UPDATE matches only the revision the client read;
    rowcount 0 means another writer got there first, so the save is refused rather
    than clobbering it. Rowcount 0 also covers 'no such user', which the route maps
    separately.
    """
    with _connection(db_path) as connection:
        if expected_revision is None:
            cursor = connection.execute(
                "UPDATE boards SET data = ?, revision = revision + 1 "
                "WHERE user_id = (SELECT id FROM users WHERE username = ?)",
                (board.model_dump_json(), username),
            )
        else:
            cursor = connection.execute(
                "UPDATE boards SET data = ?, revision = revision + 1 "
                "WHERE user_id = (SELECT id FROM users WHERE username = ?) "
                "AND revision = ?",
                (board.model_dump_json(), username, expected_revision),
            )
        if cursor.rowcount == 0 and expected_revision is not None:
            raise RevisionConflict(
                f"board changed since read (expected revision {expected_revision})"
            )
