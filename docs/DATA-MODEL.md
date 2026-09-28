# Data model

How the boards are stored. Originally written in Part 5; restructured in Part 11 for
real accounts and multiple boards per user.

## Decision

SQLite, with **one JSON blob per board**. The board's columns and cards live in a single
`TEXT` column, not in normalised tables.

The frontend already keeps the board in one normalised-in-memory structure. Storing it as
JSON means the API has no mapping layer in either direction: the same object the UI
renders is what gets validated and persisted.

The cost is accepted deliberately: you cannot ask SQL questions about the board, such as
"which cards are in the Review column". If that is ever needed, this is the decision to
revisit.

## Tables

```sql
CREATE TABLE users (
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
```

| Table | Column | Type | Notes |
|---|---|---|---|
| `users` | `id` | `INTEGER` | Primary key, autoincrement |
| `users` | `username` | `TEXT` | `UNIQUE`, the login name |
| `users` | `password_hash` | `TEXT` | `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`; empty on a migrated row until the seed backfills the demo credential |
| `boards` | `id` | `INTEGER` | Primary key, autoincrement |
| `boards` | `user_id` | `INTEGER` | FK to `users.id`, `ON DELETE CASCADE`. **Not** UNIQUE: a user owns any number of boards |
| `boards` | `name` | `TEXT` | Shown in the board switcher |
| `boards` | `data` | `TEXT` | The `BoardData` JSON |
| `boards` | `revision` | `INTEGER` | Bumped on every write; see below |

`ON DELETE CASCADE` means removing a user removes their boards.

Passwords are hashed with stdlib `hashlib.pbkdf2_hmac` (SHA-256, 240k iterations),
verified in constant time. The algorithm and cost are written into the stored string, so
raising the cost later needs no migration.

There is no `created_at` or `updated_at`. Nothing displays or sorts by time, and the
board JSON is replaced wholesale on every save.

There is a `revision` integer instead of a timestamp: it is the optimistic-concurrency
token. Every write bumps it, `GET /api/boards/{id}/board` returns it in
`X-Board-Revision`, and `PUT` / `POST /api/chat` take it as `If-Match`, answering `409`
when another writer got there first. Clients that omit `If-Match` still work.

### Migrating from the pre-Part-11 schema

Databases created before Part 11 are migrated on startup:

- `users` gains `password_hash` (ADD COLUMN). The demo `user` row's hash is backfilled
  from the old hardcoded `password`, so that credential keeps working.
- `boards` is rebuilt (SQLite cannot drop a table-level `UNIQUE(user_id)`): every row is
  copied verbatim with `name = 'Untitled board'`, keeping ids, data, and revisions.

Ids are opaque stable strings. The client mints new card ids locally with `createId` in
`frontend/src/lib/kanban.ts` and the server stores them verbatim, so ownership of id
generation stays with the client. Board ids, by contrast, are server-assigned integers.

## The JSON contract

`data` holds a `BoardData` object. It matches `frontend/src/lib/kanban.ts` field for
field.

```json
{
  "columns": [
    { "id": "col-backlog", "title": "Backlog", "cardIds": ["card-1"] },
    { "id": "col-done", "title": "Done", "cardIds": [] }
  ],
  "cards": {
    "card-1": {
      "id": "card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics.",
      "dueDate": "2026-03-01",
      "labels": ["design", "urgent"]
    }
  }
}
```

| JSON | Type | Python | TypeScript | Meaning |
|---|---|---|---|---|
| `columns` | array | `list[Column]` | `Column[]` | Columns in display order |
| `columns[].id` | string | `str` | `string` | Stable identifier |
| `columns[].title` | string | `str` | `string` | Editable, may be empty |
| `columns[].cardIds` | array of string | `list[str]` | `string[]` | Card ids, **in display order** |
| `cards` | object | `dict[str, Card]` | `Record<string, Card>` | Keyed by card id |
| `cards.*.id` | string | `str` | `string` | Same value as the key |
| `cards.*.title` | string | `str` | `string` | Card heading |
| `cards.*.details` | string | `str` | `string` | Body text |
| `cards.*.dueDate` | string or null | `date \| None` | `string \| null` | Optional ISO due date |
| `cards.*.labels` | array of string | `list[str]` | `string[]` | Optional labels; empty means none |

Two notes on shape:

- **Order is array position, not a stored index.** `columns` and each `cardIds` list are
  ordered, and that order is the display order. There is no `position` column to fall out
  of sync with the array.
- **`cardIds` is camelCase on the wire.** The Python attribute is `card_ids`; pydantic's
  `serialize_by_alias` emits `cardIds` by default, so the JSON matches the frontend
  exactly without any call site remembering to pass a flag. Do not "fix" this to
  `card_ids`, or the frontend will silently stop finding its cards.

## Invariants

Enforced by `BoardData` in `backend/app/models.py`, so an invalid board is rejected at
every entry point rather than only in one route. A violation returns HTTP 422.

1. Every id in a column's `cardIds` exists as a key in `cards`. A dangling reference would
   render as an empty or broken card.
2. Each key in `cards` equals that card's own `id`. A mismatch would render a card under
   the wrong id, which breaks drag and drop and the `data-testid` hooks.
3. A card appears in at most one column, and at most once within it. A card in two columns
   renders twice, and dragging one copy moves only that copy, leaving the board
   permanently inconsistent. This was added in Part 7 after a hand-written `PUT` that
   appended a card to a second column without removing it from the first produced exactly
   that state. Any client that appends without removing is enough to trigger it, so it is
   treated as a real failure rather than a hypothetical one.

Deliberately **not** enforced, to avoid speculative validation:

- Titles may be empty. The column rename input can genuinely be cleared by the user, so
  rejecting empty titles would break the existing UI.
- A card present in `cards` but in no column is allowed. It is invisible rather than
  broken, and no current flow creates one.
- Duplicate column ids are not rejected. Nothing produces them today.

## Not modelled

- **Chat history.** The plan keeps that in the browser, so it is not persisted.
- **Board snapshots.** Every save overwrites `data`; there is no history to roll back
  to. (Conflicting concurrent writes are detected via `revision`, above, but past
  states are not kept.)
- **Board sharing between users.** A board belongs to exactly one user. There is no
  membership table.

## Creating the database

The file is created on first use if it does not exist, and the schema is applied with
`CREATE TABLE IF NOT EXISTS`. The path is configurable, defaulting to a file inside the
container's data directory, which is a mounted volume so the board survives
`docker compose down` and image rebuilds.

On startup the app also seeds the demo `user` row (with a real password hash) and that
user's board if they have none, from the same data the frontend ships as `initialData`.
A newly **registered** user instead gets one empty board named "First board" with the
standard five columns, so a new account starts with a clean structure rather than demo
cards.

## API surface (Part 11)

- `POST /api/register {username, password}` — creates the account, seeds a board, signs in
- `POST /api/login` / `POST /api/logout` / `GET /api/me` — as before, verified against the stored hash
- `GET /api/boards` — the signed-in user's boards with card counts
- `POST /api/boards {name}` — creates a board (five empty columns)
- `PUT /api/boards/{id} {name}` — renames; `DELETE /api/boards/{id}` — deletes
- `GET` / `PUT /api/boards/{id}/board` — the `BoardData` blob, with the revision header and `If-Match` contract above
- `POST /api/chat {board_id, message, history}` — the AI edits the named board only
- `GET` / `PUT /api/board` — legacy aliases for the user's first board, kept for older clients
