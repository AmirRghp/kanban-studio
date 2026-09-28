# Backend

FastAPI application. Serves the JSON API under `/api` and the built Next.js frontend as
static files everywhere else.

## Layout

```
backend/
  pyproject.toml        uv-managed project. FastAPI + pydantic + uvicorn, pytest + httpx2 dev
  uv.lock               committed, so Docker builds are reproducible
  app/
    __init__.py
    main.py             create_app() factory, the routes, and static file serving
    config.py           Settings from the environment
    ai.py               OpenRouter client, error types, prompt constants
    chat.py             prompt building and one turn of conversation
    ops.py              the operation models, their JSON schema, and apply_operations
    auth.py             password hashing, the session user model, require_user
    db.py               SQLite schema, migrations, seeding, and the board queries
    models.py           Card, Column, BoardData. The JSON contract, see docs/DATA-MODEL.md
  tests/
    conftest.py         builds a stand-in static dir so routing is testable without a build
    test_health.py      the health endpoint
    test_static.py      index, assets, SPA fallback, traversal, unbuilt-frontend
    test_models.py      the board JSON contract and its invariants
    test_auth.py        registration, login, logout, session handling
    test_board.py       board CRUD, per-user isolation, and seed drift
    test_revision.py    If-Match / X-Board-Revision optimistic concurrency
    test_ai.py          the AI route, client, retry logic, and one live test
    test_ops.py         each operation, skipping bad ones, and the invariants
    test_chat.py        the chat route, the prompt, and one live test
    test_model_config.py  that OPENROUTER_MODEL reaches the outgoing request
```

`app` is not an installed package. It is imported by path, with `backend/` as the working
directory. This is why `pyproject.toml` sets `pythonpath = ["."]` for pytest.

## Sessions and secrets

`SESSION_SECRET` signs the session cookie. It defaults to an obviously insecure value
that is acceptable only because this runs on loopback; the lifespan logs a warning at
startup whenever the default is in use, so a deployment that left it unset is visible in
the logs. `https_only` is off for the same reason, and compose maps the port to
`127.0.0.1` only.

## Board revisions (optimistic concurrency)

The `boards` table carries a `revision` integer, bumped on every write.
`GET /api/boards/{id}/board` returns the board plus an `X-Board-Revision` header;
`PUT /api/boards/{id}/board` and `POST /api/chat` accept `If-Match` with the revision the
caller read and answer `409` when another writer got there first, so two tabs (or a chat
turn and a manual save) can no longer silently clobber each other. `save_board` /
`update_board` implement the check in `app/db.py`, which also migrates pre-revision
databases on startup. Clients that omit `If-Match` still work (the write is
unconditional).

## Current state

Parts 1-10 of `docs/PLAN.md` are implemented: static serving, sign-in, the board API with
optimistic-concurrency revisions, OpenRouter, and board-aware chat. Part 11 adds real
accounts, multiple boards per user, and card due dates and labels. The frontend is copied
into the image at `/app/app/static`. A bare checkout has no `static/` directory, so `/`
returns a 503 explaining that the frontend has not been built, rather than an opaque 500
from a missing file.

`create_app(static_dir, db_path, session_secret=None)` is a factory rather than a bare
module-level app so tests can point it at temporary directories and their own database. The
module still exports `app = create_app(STATIC_DIR, Path(get_settings().database_path))` for
uvicorn. The conftest `client` fixture enters the `TestClient` as a context manager so the
lifespan runs and the database is created and seeded, exactly as in production.

## Sessions

`SessionMiddleware` signs the cookie. The payload is base64, so it is readable but not
forgeable, which is acceptable because the only thing in it is a username.

`login` must set `request.session["username"]` and let the middleware write the cookie. Do
not call `set_cookie` by hand: the middleware will not recognise a raw cookie on the next
request, `unsign` fails, and every authenticated call returns 401. That bug landed here
briefly and `test_me_returns_the_username_when_signed_in` caught it.

`require_user` in `app/auth.py` is the dependency for every protected endpoint: `/api/me`,
all the `/api/boards` routes, the board data routes, `/api/chat`, and `/api/ai/ping`. The
signing secret comes from `SESSION_SECRET`, defaulting to an obviously insecure value that
is acceptable only because this runs on localhost. `https_only` is off for the same reason.

## Accounts and passwords

Part 11 replaced the hardcoded credential with real accounts. `auth.py` holds the whole
of it, using the stdlib only, so there is no new dependency:

- `hash_password` returns `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`. Writing the
  algorithm and cost into the stored string means both can be raised later without a
  migration. `ITERATIONS` is 240k, roughly 100 ms per verify, which is normal for an
  interactive login.
- `verify_password` parses that string and compares with `secrets.compare_digest`, so a
  wrong password cannot be told apart from a wrong username by timing. A stored value
  that does not parse is a failed verify, not a crash.
- `validate_registration` returns a human-readable reason or `None`. Username is 3-30
  characters of letters, numbers, hyphen and underscore; password is at least 8.

`db.check_credentials` looks the user up and then verifies the hash. A row with an empty
`password_hash` fails the check, which is what makes a pre-Part-11 row unusable until the
seed backfills it.

`db.create_user` lets `sqlite3.IntegrityError` out as a `UserExists`, which the route maps
to 409. Registration seeds the account with a board named "First board" holding
`EMPTY_BOARD`: the five standard columns and no cards, so a new account starts clean
rather than inheriting the demo cards.

The demo account is `user` / `password`, now a real row with a real hash, seeded by
`_seed_demo_user` on every startup. If the row exists with an empty hash, the seed
backfills it, which is how a database created before Part 11 keeps that credential
working.

## Migrations

`db.initialise` runs migrations before `executescript(SCHEMA)`, so a fresh file is
created directly at the current shape and an old file is brought forward. Every step is
guarded by a `PRAGMA table_info` check, so `initialise` stays idempotent.

- `users` gains `password_hash` with `ALTER TABLE ... ADD COLUMN`.
- `boards` gains `revision`, then is **rebuilt** if it still carries the old
  `UNIQUE(user_id)` or has no `name`. SQLite cannot drop a table-level constraint, so
  `_rebuild_boards_table` renames the table, recreates it from `SCHEMA`, copies every row
  with `name = 'Untitled board'` keeping ids, data and revisions, then drops the original.

Row ids and revisions survive a rebuild, so a client holding an `If-Match` value is not
broken by an upgrade.

## The board API

Boards are addressed by id and scoped to the signed-in user on every query.

| Route | Does |
|---|---|
| `POST /api/register` | Create the account, seed a board, sign in |
| `POST /api/login` / `POST /api/logout` / `GET /api/me` | Session lifecycle |
| `GET /api/boards` | The user's boards, oldest first, with card counts |
| `POST /api/boards` | Create a board from `EMPTY_BOARD` |
| `PUT /api/boards/{id}` | Rename. Empty name is 422 |
| `DELETE /api/boards/{id}` | Delete |
| `GET`/`PUT /api/boards/{id}/board` | The `BoardData` blob, with the revision contract |
| `POST /api/chat` | The AI edits the board named in `board_id` |
| `GET`/`PUT /api/board` | Legacy aliases for the user's **first** board |

The two legacy routes exist so a client that predates Part 11 keeps working. They resolve
the user's first board, which is always the seeded one, and delegate to the board-scoped
handlers. `include_in_schema=False` keeps them out of the OpenAPI document.

Every query goes through `db._owned_board`, which joins `boards` to `users` on
`username`. A board belonging to someone else is `BoardNotFound`, mapped to 404, so
ownership is never leaked as a distinguishable error. `rename_board` and `delete_board`
call it before writing, not after.

`PUT` validates through the same `BoardData` model as everything else, so an invalid board
returns 422 and never reaches the database.

Two implementation notes:

- **The board routes are `def`, not `async def`.** `sqlite3` is blocking, so a sync
  handler lets Starlette run it in a threadpool. Making them `async` would stall the event
  loop for every other request.
- **`SEED_BOARD` in `db.py` duplicates the frontend's `initialData`.** The frontend copy
  is TypeScript in a separate build, so it cannot be imported here.
  `test_seed_board_matches_the_frontend_initial_data` compares `SEED_BOARD` against the
  `FRONTEND_BOARD` fixture in `test_models.py`, so drift fails the suite.

The database file is created on startup, including its parent directory, and the schema
uses `IF NOT EXISTS` so `initialise` is safe to call repeatedly. The compose file mounts a
named volume at `/app/data`, so the board survives `docker compose down` and rebuilds.

## Choosing the model

The model is a setting, not a constant. `Settings.openrouter_model` reads
`OPENROUTER_MODEL` from the environment and defaults to
`dots-studio/dots-3-note-preview:free`, the model this was built against. `AiClient` carries
the model it was given, and `GET /api/ai/ping` reports the one actually in use, so there is
never a question about which model answered.

```bash
OPENROUTER_MODEL=some-vendor/some-model:free ./scripts/start.sh
```

`test_model_config.py` guards this. It asserts the environment value reaches the outgoing
request body for both plain and structured calls, and that hardcoding the model instead
fails those tests. Do not reintroduce a module-level `MODEL` constant; it silently ignores
the setting.

## OpenRouter

`app/ai.py` holds a small `AiClient` that posts to OpenRouter's chat completions endpoint
with `httpx2`. It exposes one method, `complete(messages) -> str`, which is the shape
Part 9 needs for conversation history.

Failures are typed so routes can map them without inspecting strings:

| Exception | Meaning | Route status |
|---|---|---|
| `AiNotConfigured` | no `OPENROUTER_API_KEY` | 503 |
| `AiUnavailable` | upstream failed, timed out, or replied unusably | 502 |

`GET /api/ai/ping` asks the model what 2+2 is and returns the answer with the model name.
It requires a session, because it spends the API key and the rest of the API is protected.

Two behaviours worth keeping:

- **One retry, and only for retryable failures.** A 5xx or a timeout is worth one more
  attempt because the model is free tier and can be briefly busy. A 401 or 403 is not,
  because a bad key will still be bad, so it fails immediately. `MAX_ATTEMPTS = 2` and
  `RETRY_DELAY_SECONDS = 1.0` are module constants.
- **The API key is never logged and never appears in an error.** `test_the_api_key_is_
  never_logged` and `test_the_api_key_is_never_in_an_error_message` guard both. The
  success log records the model name and completion token count only.

`logging.basicConfig` is called in the lifespan, not at import. Without it the root logger
sits at WARNING and the usage line in `ai.py` is silently dropped, which is easy to miss
because nothing fails.

### Testing the AI

`httpx2.MockTransport` is injected into `AiClient`, so the retry, error-mapping, and
key-hygiene tests make no network calls. Route tests replace the client through
`app.dependency_overrides[get_ai_client]`.

The one test that really calls OpenRouter is marked `live` and is skipped unless
`RUN_LIVE=1`:

```bash
cd backend && RUN_LIVE=1 uv run pytest -m live     # or, in Docker:
docker compose --profile test run --rm -e RUN_LIVE=1 backend-test uv run --no-sync pytest -m live
```

It skips itself if `OPENROUTER_API_KEY` is unset, so it is safe to run anywhere.

## The AI editing the board

`POST /api/chat` takes `{board_id, message, history}` and returns `{reply, board, warnings}`.
`board_id` is required, not optional: the AI must be told which board to edit, and the
route resolves it against the signed-in user, so a caller cannot aim it at someone else's
board.

**The model is asked what to change, never trusted to return the board.** It replies with
a `reply` plus a list of operations, and `ops.apply_operations` applies each one to the
stored board. Anything that cannot be applied is skipped and reported in `warnings`; the
board that comes back is the one on disk, so a bad reply costs at most the operations that
were skipped.

`CHAT_RESPONSE_SCHEMA` is derived from the pydantic models with
`ChatResponse.model_json_schema()`, so the schema sent to the model and the parser that
reads the reply cannot drift apart. Do not hand-write a second copy.

`create_card` never takes a card id from the model. `ops.new_card_id()` mints one, so a
model-chosen id can never collide with an existing card or break the board's invariants.
(The interactive UI deliberately mints ids client-side instead; that is a different
writer with different constraints, see `docs/DATA-MODEL.md`.)

`create_card` and `update_card` also accept optional `due_date` and `labels`, so the AI can
set them. Two details in `UpdateCard` are load-bearing:

- **Absent means "keep what is there".** `update_card` replaces the card wholesale, so a
  model that only meant to fix a typo would otherwise silently wipe the due date.
  `_update_card` consults `operation.model_fields_set`, which pydantic fills with exactly
  the keys the reply contained, and writes only those two fields.
- **Blank labels are dropped** by a `field_validator(mode="before")`, so an empty string
  cannot become a chip that renders as nothing.

Do **not** reintroduce `due_date_set` / `labels_set` boolean fields. That is what this
code used to carry, and it was silently broken: nothing ever set them, so a model asking
to change a due date got a confident reply and an unchanged card. Pydantic already tracks
the distinction, and a companion flag could only ever be trusted to the model.
`test_a_due_date_from_the_model_is_applied` and
`test_the_due_date_flags_are_not_part_of_the_wire_contract` both fail if it returns, and
they go through `ChatResponse.model_validate` deliberately, since a hand-built
`UpdateCard` skips the parse step where "absent" is decided.

`db.update_board` does the read, the transform, and the write in a single transaction, so a
chat cannot interleave with a manual save and clobber it. The prompt is built from a
separate read, so the operations are always applied to the current board rather than to a
snapshot.

### What the model actually does

Measured with live probes before the feature was built, six prompts per shape, three runs
per case on the ambiguous ones:

| Schema shape | Valid ids |
|---|---|
| flat object, every field required, strict | 5/6, and it invented `card_id` on create |
| discriminated union, strict | **11/12** |
| discriminated union, lenient | 10/12 |

The flat shape fails because strict mode forces a `card_id` on every operation, including
`create_card`, and the model invents one to fill it. The discriminated union cannot express
that field, which is exactly why it works. Strict mode also beat lenient on semantics.

So the union wins, and it is what `CHAT_RESPONSE_SCHEMA` produces.

### The discriminator key

The model must name the operation type, and the reply schema discriminates on `op`. Not
every model honours that name. `stealth/space-bunny-alpha` returns correct,
fully schema-shaped replies, but on different calls named that field `op`, then `action`,
then `operation`, for the same request. Every other field, including all ids, was correct
every time.

`ops.normalise_reply` recovers it: the operation is identified by its *value*, which is
always one of the five known names, rather than by guessing a list of possible key names.
A reply is rewritten only when exactly one non-data field holds a known name, so a card
genuinely titled `create_card` is not mistaken for a discriminator, and an ambiguous reply
is left alone to fail validation loudly.

Without this, every `create_card` from that model was discarded with a warning while the
user was told the card had been added. With it, all five operations and a no-op request
were clean across seven consecutive live calls.

**The model is still wrong roughly one time in twelve.** Ids are reliable; intent is not. In
one probe a request to move a card came back as `create_card`, which would create a card
instead of moving one. No id validation catches that, because both ids are valid. This is a
property of a small free fine-tune, not something the backend can fix cheaply. The honest
mitigations in place are that the user sees the reply next to the resulting board, and Part
10 shows skipped operations as warnings. If it proves too wrong in use, the next step is a
retry when the applied operations do not match the intent, not a better prompt alone.

### Live tests and the free tier

Both `live` tests skip when OpenRouter answers 429, because a rate-limited provider is not a
defect here and must not take the suite down. During development the free tier rate-limited
hard enough that several live runs in a row failed, which is what those skips are for. The
retry in `AiClient` buys one immediate re-attempt, which is not enough for a multi-minute
quota window.

## The board data model

`app/models.py` defines `Card`, `Column` and `BoardData`, and is the single source of truth
for the wire format. The full design, including the SQL schema and the reasoning behind
it, is in `docs/DATA-MODEL.md`. Two things to get right:

- **`cardIds` is camelCase on the wire, `card_ids` in Python.** `Column` uses
  `Field(alias="cardIds")` with `ConfigDict(populate_by_name=True, serialize_by_alias=True)`,
  so `model_dump()` emits `cardIds` by default and no call site has to remember a flag. Do
  not switch to `by_alias=False`, and do not rename the field to `cardIds`. Either breaks
  the frontend contract, and it breaks it quietly.
- **Integrity lives in the model, not in a route.** `BoardData.check_references` rejects
  `cardIds` entries with no matching card, and `cards` keys that disagree with the card's
  own `id`. Keeping these in the model means every future entry point, including the AI
  path in Part 9, inherits them for free.

`test_models.py` embeds the frontend's `initialData` verbatim, so a change to the
frontend's data model fails the backend suite rather than surfacing at runtime.

### Route order matters

Do not rearrange these. FastAPI matches in registration order, so the catch-all must stay
last:

1. `GET /api/health`
2. `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/me`
3. `GET`/`POST /api/boards`, `PUT`/`DELETE /api/boards/{id}`,
   `GET`/`PUT /api/boards/{id}/board`, the legacy `GET`/`PUT /api/board`,
   `POST /api/chat`, `GET /api/ai/ping`
4. `GET /api/{rest:path}` — 404 for unknown API routes, so a typo returns a JSON 404
   instead of the SPA's HTML with a 200
5. `mount("/_next", ...)` — assets, via `StaticFiles`
6. `GET /{full_path:path}` — serves a real file if one exists, otherwise `index.html`

### The path traversal guard

The static handler resolves the requested path and checks
`candidate.is_relative_to(static_dir.resolve())` before serving it. Without that check, a
request for `/../secret.txt` serves files from outside the static directory.
`test_path_traversal_does_not_escape_the_static_dir` is the regression test; it must fail
if the check is removed.

That test drives the ASGI app directly rather than going through `TestClient`, because an
HTTP client resolves `..` before the request leaves it, so a traversal attempt made
through the normal client never reaches the handler.

## Commands

Everything runs through Docker, from the project root:

```bash
./scripts/test.sh                                        # all suites
docker compose --profile test run --rm backend-test      # pytest only
```

The host cannot run `uv run`: it prepends the venv's `bin` to `PATH` and re-parses that as
a colon-separated list, so the colon in this checkout path yields
`error: path segment contains separator ':'`. `uv sync` and the venv interpreter itself are
unaffected, so `uv sync && ./.venv/bin/python -m pytest` still works for a fast local loop.
Do not hardcode a path in `pyproject.toml` to work around this.

## Dependencies

Chosen as the latest stable releases at the time of writing. Two notes:

- **`httpx2`, not `httpx`.** It is a **runtime** dependency, not a dev one, because
  `app/ai.py` makes outbound calls with it. It was briefly a dev dependency and the app
  image crashed on startup with `ModuleNotFoundError: No module named 'httpx2'`, since
  the app stage installs with `--no-dev`. Keep it in `dependencies`.
- Starlette 1.7 emits
  `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
  install httpx2 instead`. `fastapi.testclient.TestClient` works with `httpx2` and the
  warning disappears. Do not reintroduce `httpx` for test code.
- `pydantic-settings` is a runtime dependency: `app/config.py` reads settings through
  it. `httpx2` is also runtime, not dev, for the same reason.

## Conventions

- Latest stable library versions; simplest implementation that works.
- Tests use `fastapi.testclient.TestClient`, so no server or network is needed.
- Anything touching OpenRouter must be mocked in tests. Tests that hit the real API are
  marked `live` and skipped by default.
- Never log or return `OPENROUTER_API_KEY`. It arrives as a runtime environment variable
  and is never baked into an image layer.
- When a test is meant to catch a specific defect, verify it actually fails when the
  defect is reintroduced. A test that cannot fail is worse than no test.
