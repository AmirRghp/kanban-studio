# Data model

How the Kanban board is stored. Written in Part 5, implemented in Part 6.

## Decision

SQLite, with **one JSON blob per board**. The board's columns and cards live in a single
`TEXT` column, not in normalised tables.

The frontend already keeps the board in one normalised-in-memory structure, and the MVP has
one board per user. Storing it as JSON means the API has no mapping layer in either
direction: the same object the UI renders is what gets validated and persisted.

The cost is accepted deliberately: you cannot ask SQL questions about the board, such as
"which cards are in the Review column" or "how many cards were added this week". If that
is ever needed, this is the decision to revisit.

## Tables

```sql
CREATE TABLE users (
    id       INTEGER PRIMARY KEY,
    username TEXT    NOT NULL UNIQUE
);

CREATE TABLE boards (
    id       INTEGER PRIMARY KEY,
    user_id  INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    data     TEXT    NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
```

| Table | Column | Type | Notes |
|---|---|---|---|
| `users` | `id` | `INTEGER` | Primary key, autoincrement |
| `users` | `username` | `TEXT` | `UNIQUE`, the login name |
| `boards` | `id` | `INTEGER` | Primary key, autoincrement |
| `boards` | `user_id` | `INTEGER` | `UNIQUE`, FK to `users.id`, `ON DELETE CASCADE` |
| `boards` | `data` | `TEXT` | The `BoardData` JSON |
| `boards` | `revision` | `INTEGER` | Bumped on every write; see below |

Why the table is named `boards` while `user_id` is `UNIQUE`: the MVP allows one board per
user, but naming it `boards` leaves room for more later without a migration. The `UNIQUE`
constraint is what enforces the MVP rule, and dropping it is the whole change needed to
support multiple boards.

`ON DELETE CASCADE` means removing a user removes their board, so there is no orphaned
JSON left behind.

There is no `created_at` or `updated_at`. Nothing in the MVP displays or sorts by time, and
the board JSON is replaced wholesale on every save, so a row-level timestamp would only
ever record the last write. Add them when something needs them.

There is a `revision` integer instead of a timestamp: it is the optimistic-concurrency
token. Every write bumps it, `GET /api/board` returns it in `X-Board-Revision`, and
`PUT /api/board` / `POST /api/chat` take it as `If-Match`, answering `409` when another
writer got there first. Databases created before the column existed are migrated on
startup (`ALTER TABLE ... ADD COLUMN`), and clients that omit `If-Match` still work.

Ids are opaque stable strings. The client mints new card ids locally with `createId` in
`frontend/src/lib/kanban.ts` and the server stores them verbatim, so ownership of id
generation stays with the client. A server-generated id would be the change to make if
ids ever need to be unguessable or globally unique.

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
      "details": "Draft quarterly themes with impact statements and metrics."
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

- **Users and passwords.** Part 4 hardcodes `user` / `password`. The `users` table exists
  so multiple users are possible later, but no credential columns are defined yet, and no
  password hash is stored. Deciding on hashing is Part 4's job.
- **Chat history.** Part 9 sends conversation history to the model. The plan keeps that in
  the browser, so it is not persisted.
- **Board snapshots.** Every save overwrites `data`; there is no history to roll back
  to. (Conflicting concurrent writes are detected via `revision`, above, but past
  states are not kept.)

## Creating the database

The file is created on first use if it does not exist, and the schema is applied with
`CREATE TABLE IF NOT EXISTS`. The path is configurable, defaulting to a file inside the
container's data directory, which is a mounted volume so the board survives
`docker compose down` and image rebuilds.

On startup the app also seeds the single `user` row, and that user's board if they have
none, from the same data the frontend ships as `initialData`. A fresh database therefore
comes up with a working board rather than an empty one.
