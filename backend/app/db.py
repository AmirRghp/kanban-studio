import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from app.auth import hash_password, verify_password
from app.models import BoardData

# Mirrors docs/DATA-MODEL.md. IF NOT EXISTS keeps startup idempotent.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS boards (
    id       INTEGER PRIMARY KEY,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name     TEXT    NOT NULL DEFAULT 'Untitled board',
    data     TEXT    NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
"""

# Old databases are brought up to the current schema on startup. Each entry is guarded
# by a pragma / column check, so running initialise repeatedly is safe.
# The old boards table had UNIQUE(user_id), one board per user. SQLite cannot drop a
# table constraint, so the table is rebuilt, copying every row verbatim.


def _add_revision_column_if_missing(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(boards)").fetchall()
    }
    if "revision" not in columns:
        connection.execute(
            "ALTER TABLE boards ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"
        )


def _migrate_users_table(connection: sqlite3.Connection) -> None:
    # The pre-Part-11 users table had no password_hash column. A plain ADD COLUMN
    # leaves the demo user's hash empty, which _seed_demo_user backfills.
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "password_hash" not in columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''"
        )


def _boards_table_needs_rebuild(connection: sqlite3.Connection) -> bool:
    """Old schema: UNIQUE(user_id) allowed one board per user, and there was no name.

    SQLite cannot drop a table constraint in place, so the table is rebuilt instead.
    """
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(boards)").fetchall()
    }
    if "name" not in columns:
        return True
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'boards'"
    ).fetchone()
    return sql is not None and "UNIQUE" in (sql["sql"] or "").upper()


def _rebuild_boards_table(connection: sqlite3.Connection) -> None:
    connection.execute("ALTER TABLE boards RENAME TO boards_old")
    connection.executescript(SCHEMA)
    connection.execute(
        "INSERT INTO boards (id, user_id, name, data, revision) "
        "SELECT id, user_id, 'Untitled board', data, revision FROM boards_old"
    )
    connection.execute("DROP TABLE boards_old")


# One busy timeout in one place. Two writers both doing read-modify-write inside
# update_board will serialize here instead of throwing 'database is locked'.
_BUSY_TIMEOUT_SECONDS = 5.0


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

# A new board starts with the standard five columns and no cards.
EMPTY_BOARD = BoardData(
    columns=[
        {"id": "col-backlog", "title": "Backlog", "cardIds": []},
        {"id": "col-discovery", "title": "Discovery", "cardIds": []},
        {"id": "col-progress", "title": "In Progress", "cardIds": []},
        {"id": "col-review", "title": "Review", "cardIds": []},
        {"id": "col-done", "title": "Done", "cardIds": []},
    ],
    cards={},
)

DEMO_USERNAME = "user"
DEMO_PASSWORD = "password"


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
    """Create the database and schema if absent, migrate old schemas, seed the demo user."""
    with _connection(db_path) as connection:
        # Migrations run before executescript so the new-schema tables are created
        # directly at the current shape on a fresh file.
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='boards'"
        ).fetchone():
            _migrate_users_table(connection)
            _add_revision_column_if_missing(connection)
            if _boards_table_needs_rebuild(connection):
                _rebuild_boards_table(connection)
        connection.executescript(SCHEMA)
        _seed_demo_user(connection)


def _seed_demo_user(connection: sqlite3.Connection) -> None:
    """Seed the demo user and its board, backfilling the password hash if missing."""
    connection.execute(
        "INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)",
        (DEMO_USERNAME, hash_password(DEMO_PASSWORD)),
    )
    row = connection.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (DEMO_USERNAME,)
    ).fetchone()
    if not row["password_hash"]:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(DEMO_PASSWORD), row["id"]),
        )
    has_board = connection.execute(
        "SELECT 1 FROM boards WHERE user_id = ?", (row["id"],)
    ).fetchone()
    if not has_board:
        connection.execute(
            "INSERT INTO boards (user_id, name, data) VALUES (?, ?, ?)",
            (row["id"], "First board", SEED_BOARD.model_dump_json()),
        )


class UserExists(Exception):
    """Registration found the username already taken."""


class InvalidCredentials(Exception):
    """Login failed."""


def create_user(db_path: Path, username: str, password: str) -> int:
    """Register a user; raises UserExists when the name is taken."""
    with _connection(db_path) as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hash_password(password)),
            )
        except sqlite3.IntegrityError as exc:
            raise UserExists(f"username {username!r} is taken") from exc
        return cursor.lastrowid  # type: ignore[return-value]


def get_user_id(db_path: Path, username: str) -> int | None:
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row["id"] if row else None


def check_credentials(db_path: Path, username: str, password: str) -> bool:
    """Verify against the stored hash. A missing user fails without a hash to check."""
    with _connection(db_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not row["password_hash"]:
        return False
    return verify_password(password, row["password_hash"])


def create_board(db_path: Path, user_id: int, name: str, board: BoardData) -> int:
    with _connection(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO boards (user_id, name, data) VALUES (?, ?, ?)",
            (user_id, name, board.model_dump_json()),
        )
        return cursor.lastrowid  # type: ignore[return-value]


class BoardNotFound(Exception):
    """No such board, or the board belongs to another user."""


def _owned_board(connection: sqlite3.Connection, board_id: int, username: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT boards.* FROM boards "
        "JOIN users ON users.id = boards.user_id "
        "WHERE boards.id = ? AND users.username = ?",
        (board_id, username),
    ).fetchone()
    if row is None:
        raise BoardNotFound(f"no board {board_id} for user {username!r}")
    return row


def list_boards(db_path: Path, username: str) -> list[dict]:
    """The user's boards, oldest first, with card counts for the switcher."""
    with _connection(db_path) as connection:
        rows = connection.execute(
            "SELECT boards.id, boards.name, boards.data FROM boards "
            "JOIN users ON users.id = boards.user_id "
            "WHERE users.username = ? ORDER BY boards.id",
            (username,),
        ).fetchall()
    result = []
    for row in rows:
        board = BoardData.model_validate_json(row["data"])
        result.append(
            {"id": row["id"], "name": row["name"], "cardCount": len(board.cards)}
        )
    return result


def rename_board(db_path: Path, username: str, board_id: int, name: str) -> None:
    with _connection(db_path) as connection:
        _owned_board(connection, board_id, username)
        connection.execute(
            "UPDATE boards SET name = ? WHERE id = ?", (name, board_id)
        )


def delete_board(db_path: Path, username: str, board_id: int) -> None:
    with _connection(db_path) as connection:
        _owned_board(connection, board_id, username)
        connection.execute("DELETE FROM boards WHERE id = ?", (board_id,))


def load_board_with_revision(
    db_path: Path, username: str, board_id: int
) -> tuple[BoardData, int] | None:
    """The board plus its current revision, for optimistic concurrency on the API."""
    with _connection(db_path) as connection:
        try:
            row = _owned_board(connection, board_id, username)
        except BoardNotFound:
            return None
    if row is None:
        return None
    return BoardData.model_validate_json(row["data"]), row["revision"]


class RevisionConflict(Exception):
    """Another writer changed the board between our read and our write."""


def update_board(
    db_path: Path,
    username: str,
    board_id: int,
    change: Callable[[BoardData], BoardData],
    expected_revision: int | None = None,
) -> tuple[BoardData, int]:
    """Read, transform, and write in one transaction, returning the new revision.

    The chat path uses this so a conversation cannot clobber a board change made
    between its own read and write. With expected_revision set, a change made after
    the caller's read raises RevisionConflict instead of being applied on top of it.
    """
    with _connection(db_path) as connection:
        row = _owned_board(connection, board_id, username)

        if expected_revision is not None and row["revision"] != expected_revision:
            raise RevisionConflict(
                f"board changed since read (expected revision {expected_revision}, "
                f"current is {row['revision']})"
            )

        updated = change(BoardData.model_validate_json(row["data"]))
        new_revision = row["revision"] + 1
        connection.execute(
            "UPDATE boards SET data = ?, revision = ? WHERE id = ?",
            (updated.model_dump_json(), new_revision, board_id),
        )
        return updated, new_revision


def save_board(
    db_path: Path,
    username: str,
    board_id: int,
    board: BoardData,
    expected_revision: int | None = None,
) -> None:
    """Replace the stored board, bumping the revision.

    With expected_revision set, the UPDATE matches only the revision the client read;
    rowcount 0 means another writer got there first, so the save is refused rather
    than clobbering it. Rowcount 0 also covers 'no such board', which the route maps
    separately.
    """
    with _connection(db_path) as connection:
        _owned_board(connection, board_id, username)
        if expected_revision is None:
            cursor = connection.execute(
                "UPDATE boards SET data = ?, revision = revision + 1 WHERE id = ?",
                (board.model_dump_json(), board_id),
            )
        else:
            cursor = connection.execute(
                "UPDATE boards SET data = ?, revision = revision + 1 "
                "WHERE id = ? AND revision = ?",
                (board.model_dump_json(), board_id, expected_revision),
            )
        if cursor.rowcount == 0 and expected_revision is not None:
            raise RevisionConflict(
                f"board changed since read (expected revision {expected_revision})"
            )
