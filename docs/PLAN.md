# Project plan: Project Management MVP

Ten parts, executed in order. Each part lists substeps as checkboxes for the agent to tick
off, the tests to write, and the success criteria that must hold before moving on. Parts
marked **GATE** require explicit user sign-off before the next part starts.

Update the checkboxes as work completes. Do not tick a box that has not been verified by a
passing test or a manual check described in that part.

## Locked decisions

Agreed with the user before Part 1 was written. Do not revisit without asking.

| Area | Decision | Why |
|---|---|---|
| Storage | SQLite, one JSON blob per board: `users(id, username)` + `boards(id, user_id UNIQUE, data TEXT)` where `data` holds the full `BoardData` JSON | PLAN Part 5 says "saving it as JSON"; the frontend shape serializes directly, so there is no mapping code |
| AI mutations | The AI returns a validated list of operations, never a whole new board | A weak model cannot silently drop cards, and ops cost far fewer tokens than resending the board |
| Auth | Hardcoded `user`/`password`, server-side session in an HttpOnly signed cookie, frontend gates on `GET /api/me` | Keeps the credential out of JS-reachable storage; trivially revocable |
| Persistence | `GET /api/board` on load, then a debounced (~500 ms) whole-board `PUT /api/board` | One write path; column rename fires per keystroke so any per-action scheme needs debouncing anyway |
| Scripts | `scripts/start.sh` and `scripts/stop.sh` wrapping `docker compose up --build` / `down` | Matches AGENTS.md: the MVP runs locally in a container |
| Chat history | Lives only in the browser, in React state. Nothing is stored server-side or on disk, so a refresh or a closed tab ends the conversation | Decided by the user. The database holds the board and nothing else, so a conversation cannot outlive the tab or leak between users |
| History sent to the model | The most recent 20 messages, oldest dropped | Decided by the user. Keeps the prompt bounded however long the chat gets; a kanban task does not need the full back-catalogue |
| Starting over | A "New chat" control clears the conversation and starts fresh | Decided by the user. It resets the transcript only, never the board |

## Global conventions

- Backend listens on **8000**. Frontend dev server on 3000. The container publishes 8000.
- Backend tests: `uv run pytest` from `backend/`. No live server or network needed; the
  OpenRouter client is always mocked except where a test is explicitly marked live.
- Frontend unit tests: `npm run test:unit` from `frontend/`.
- Frontend e2e: `npm run test:e2e` from `frontend/`, against the running container.
- Lint: `npm run lint` from `frontend/`.
- `.env` at the project root is read by the backend only. It must never be exposed to the
  frontend or baked into the image.
- Per the root AGENTS.md: latest library versions, simplest possible implementation, no
  defensive programming, no emojis, concise docs.

## Target layout

```
pm/
  Dockerfile              multi-stage: node build -> python runtime
  docker-compose.yml
  .env                    OPENROUTER_API_KEY (gitignored)
  AGENTS.md
  backend/
    pyproject.toml        uv-managed
    app/
      main.py             FastAPI app, mounts API router and static frontend
      config.py           settings from environment
      db.py               sqlite connection, schema creation
      models.py           pydantic request/response models
      auth.py             login, session cookie, current-user dependency
      ai.py               OpenRouter client and prompt construction
      ops.py              applies validated AI operations to a board
      routes/             auth.py, board.py, chat.py
    tests/
  frontend/               existing Next.js app, see frontend/AGENTS.md
  scripts/
    start.sh
    stop.sh
  docs/
    PLAN.md
    DATA-MODEL.md         written in Part 5
```

---

## Part 1: Plan

Enrich this document, describe the existing frontend in `frontend/AGENTS.md`, and get user
approval.

- [x] Review root `AGENTS.md` and record the constraints it imposes
- [x] Inventory the existing frontend and record it in `frontend/AGENTS.md`
- [x] Verify the toolchain is present (Docker, Compose, Node, npm, uv, Python)
- [x] Verify the chosen model exists on OpenRouter and supports structured outputs
- [x] Resolve open design questions with the user
- [x] Enrich this document with substeps, tests, and success criteria
- [x] Obtain user approval of this plan

Tests: none. This part produces documentation only.

Success criteria:
- [x] `docs/PLAN.md` gives every part substeps, tests, and success criteria
- [x] `frontend/AGENTS.md` accurately describes the existing code, its conventions, and
      the seams later parts depend on
- [x] The user has approved the plan

**GATE: the user must approve this document before Part 2 begins.**

---

## Part 2: Scaffolding

Docker infrastructure, a FastAPI backend, and start/stop scripts. Proves the whole
toolchain works before any product code is written.

Substeps:

- [x] `backend/pyproject.toml` with FastAPI, uvicorn, pytest, and `httpx2`, managed by `uv`
- [x] `backend/uv.lock` committed so Docker builds are reproducible
- [x] `backend/app/main.py` exposing `GET /api/health` returning `{"status": "ok"}`
- [x] `backend/app/main.py` serving a placeholder static page at `/` for this part only
- [x] `Dockerfile` with a single Python 3.13 stage installing deps with `uv`
- [x] `docker-compose.yml` publishing 8000 and passing `OPENROUTER_API_KEY` from the root
      `.env`
- [x] A `healthcheck` in `docker-compose.yml`, without which `up --wait` returns before
      uvicorn binds the port and `start.sh` reports success too early
- [x] `scripts/start.sh` and `scripts/stop.sh`, executable, with clear output
- [x] `backend/AGENTS.md` and `scripts/AGENTS.md` updated to describe what now exists
- [x] Root `README.md` covering how to start, stop, and run tests

Deviations from the original Part 2 text, both deliberate:

- **The Dockerfile has one stage, not two.** The Node stage is pointless until Part 3 sets
  `output: "export"`; before that `npm run build` produces a server build with no `out/`
  to copy. The Node stage is added in Part 3.
- **`pydantic-settings` and `app/config.py` are deferred.** Nothing in Part 2 reads
  configuration, so they arrive in Part 4 with the session secret. `httpx` was replaced
  with `httpx2` because Starlette 1.7 deprecates it for `TestClient`.

Tests:
- [x] `GET /api/health` returns 200 and `{"status": "ok"}`
- [x] A smoke test asserts `GET /` returns HTML

Success criteria:
- [x] `./scripts/start.sh` brings the app up on `http://localhost:8000`
- [x] `curl http://localhost:8000/api/health` returns `{"status":"ok"}`
- [x] `curl http://localhost:8000/` returns HTML
- [x] `./scripts/stop.sh` stops it cleanly and leaves no container running
- [x] The image does not contain `OPENROUTER_API_KEY` in any layer

---

## Part 3: Add in Frontend

The real Next.js app is statically built and served by FastAPI at `/`.

Substeps:

- [x] Set `output: "export"` (and `images.unoptimized`) in `frontend/next.config.ts`
- [x] Build and confirm `frontend/out/` is produced
- [x] Root `.dockerignore` excluding `node_modules`, `.next`, `out` and `.env`
- [x] `Dockerfile` gains a `node:24-alpine` stage; `out/` is copied to `app/static`
- [x] `app/main.py` refactored to a `create_app(static_dir)` factory
- [x] FastAPI serves `out/` at `/` with `/_next` mounted for assets
- [x] Unknown paths fall back to `index.html`; unknown `/api` paths return JSON 404
- [x] The Part 2 placeholder route is removed
- [x] `frontend/playwright.config.ts` `baseURL` repointed at 8000 via `BASE_URL`, and the
      `webServer` block removed since there is no longer a Next.js server
- [x] Update `frontend/AGENTS.md`, `backend/AGENTS.md`, `scripts/AGENTS.md`, `README.md`

Tests:
- [x] Existing 3 Vitest and 3 Playwright tests still pass unchanged
- [x] Playwright asserts the "Kanban Studio" heading and 5 columns render against the
      container
- [x] A test asserts a `/_next/static/...` asset returns 200 and correct content type
- [x] A test asserts the served HTML references the built JS bundle
- [x] A test asserts a real file such as `favicon.ico` is served instead of the index
- [x] A test asserts a path traversal cannot read a file outside the static dir, and
      that the test fails if the guard is removed

Deviations from the original Part 3 text:

- **`npm run test:e2e` is no longer a host command.** `npm ci` cannot complete at this
  checkout path: the colon in `AI Coder: Vibe Coder to Agentic Engineer` breaks it with
  `napi-postinstall: not found` while linking `node_modules/.bin`. Proven by running the
  identical install on a colon-free copy, where it succeeds. All frontend tooling moved
  into Docker behind a `test` compose profile, with `scripts/test.sh` as the single entry
  point. The same colon breaks host `uv run`, so the backend suite moved into Docker too,
  for one consistent way to run tests.
- **A `503` guard was added** for a missing `index.html`, so a checkout with no build
  reports that the frontend has not been built instead of raising a bare 500.

Success criteria:
- [x] `http://localhost:8000/` shows the working Kanban board with drag and drop
- [x] No Next.js server process runs; FastAPI is the only server
- [x] The e2e suite passes against the container
- [x] CSS and self-hosted fonts load, verified by screenshot

Checkpoint:
- [x] Frontend is genuinely static; nothing in the served page needs a Node runtime

---

## Part 4: Add a fake user sign in experience

Hitting `/` while signed out shows a login form. Credentials are `user` / `password`.
Logout returns to the login form.

Substeps:

- [x] `app/config.py` with `Settings`, adding `pydantic-settings`
- [x] `app/auth.py` with the hardcoded credentials, constant-time comparison, and the
      `require_user` dependency
- [x] `POST /api/login` verifying the hardcoded credentials
- [x] Session issued as an HttpOnly, SameSite=Lax cookie via `SessionMiddleware`
- [x] `POST /api/logout` clearing the session
- [x] `GET /api/me` returning the current username, guarded by `require_user`
- [x] `itsdangerous` declared explicitly, since Starlette 1.7 no longer installs it
- [x] `SESSION_SECRET` plumbed through docker-compose, defaulting to a documented dev value
- [x] `frontend/src/lib/api.ts` with the three auth calls
- [x] `frontend/src/components/LoginView.tsx` and `App.tsx` as the session gate
- [x] Frontend login view rendered at `/` when signed out, with neither view rendered
      while `GET /api/me` is in flight
- [x] An optional sign-out control in the board header
- [x] Update `frontend/AGENTS.md`, `backend/AGENTS.md`, `README.md`

Tests:
- [x] `POST /api/login` with correct credentials sets the cookie and returns the username
- [x] The cookie is HttpOnly and SameSite=Lax
- [x] `POST /api/login` with a wrong password or username returns 401 and sets no cookie
- [x] `POST /api/logout` clears the session
- [x] `GET /api/me` without a cookie returns 401
- [x] `GET /api/me` with a valid cookie returns the username
- [x] A forged raw cookie is rejected
- [x] A validly signed cookie from a different secret is rejected, with a sanity check
      that the cookie really is valid for the app that minted it
- [x] A malformed login body returns 422
- [x] RTL: signed-out renders the login form and not the board
- [x] RTL: neither view renders while the session check is in flight
- [x] RTL: successful login swaps to the board
- [x] RTL: bad credentials show an error and stay on the login form
- [x] RTL: logout returns to the login form
- [x] Playwright: signed-out visitors see the login form and zero columns
- [x] Playwright: sign in, reload keeps the session, sign out locks the board away

Notes on what the tests caught:

- `login` originally set a raw cookie by hand while `SessionMiddleware` expects a signed
  one, so login appeared to succeed and every later call 401'd. Caught by
  `test_me_returns_the_username_when_signed_in`.
- The e2e error assertion originally used `getByRole("alert")`, which also matches Next.js's
  `__next-route-announcer__`. Caught by Playwright strict mode; now uses a `data-testid`.

Success criteria:
- [x] Visiting `/` signed out shows the login form; the board is not rendered
- [x] `user` / `password` signs in; anything else is rejected
- [x] Reloading the page keeps the user signed in
- [x] Logout works and the board is no longer reachable without signing in again
- [x] Verified against the running container with curl, and visually by screenshot

---

## Part 5: Database modeling

Propose the schema, document it, get sign-off. No implementation beyond what is needed to
prove the model.

Decided already: one JSON blob per board. This part documents it precisely.

Substeps:

- [x] Write `docs/DATA-MODEL.md` covering tables, columns, types, and constraints
- [x] Specify the `users` table: `id` primary key, `username` unique
- [x] Specify the `boards` table: `id` primary key, `user_id` unique foreign key to
      `users` with `ON DELETE CASCADE`, `data` text holding the `BoardData` JSON
- [x] Specify the `BoardData` JSON contract, matching `src/lib/kanban.ts` exactly
- [x] Implement `app/models.py`: `Card`, `Column`, `BoardData`, mirroring the frontend
- [x] Enforce the two integrity invariants in the model, not in a route, so every entry
      point rejects an invalid board
- [x] State that order is array position, so no `position` column is needed
- [x] State that ids are stable strings owned by the server once Part 6 lands
- [x] Document how a new database file is created on first run
- [x] Document the trade-off accepted by storing a blob: no SQL-level querying by column
- [x] State what is deliberately not modelled, and why
- [x] Declare `pydantic` explicitly in `pyproject.toml` rather than relying on it
      transitively through FastAPI
- [x] Update `backend/AGENTS.md`

Tests:
- [x] Round-trip test: a board serialises to JSON and deserialises without loss
- [x] A contract test asserting the wire format uses `cardIds`, not `card_ids`
- [x] A test asserting the model accepts the frontend's exact `initialData` shape, so a
      frontend data-model change fails here
- [x] Tests asserting both invariants reject their violations
- [x] Tests asserting an empty board and an empty column are valid

Success criteria:
- [x] `docs/DATA-MODEL.md` is complete enough to implement from without questions
- [x] The documented JSON contract matches the frontend types field for field
- [x] `pydantic` is a declared dependency, not an implicit one

**GATE: the user must sign off on `docs/DATA-MODEL.md` before Part 6 begins.**

---

## Part 6: Backend

API routes to read and change a user's board. The database is created if absent.

Substeps:

- [x] `db.py` opening SQLite, creating the schema on startup if missing, using
      `DATABASE_PATH` with a default of `./data/app.db`
- [x] Schema and initialisation run in the FastAPI lifespan, not at import time
- [x] Seed the single `user` account and that user's board on first run, so a fresh
      database produces a usable board
- [x] `GET /api/board` returning the current user's `BoardData`
- [x] `PUT /api/board` validating and storing a full board
- [x] Reuse the `BoardData` invariants from Part 5, so a malformed payload cannot
      corrupt stored state
- [x] `require_user` applied to both routes, and both scoped by the session username
- [x] Board routes declared as sync `def` so blocking sqlite calls run in a threadpool
- [x] A named compose volume at `/app/data` so the database survives a restart
- [x] A test asserting the backend seed board still matches the frontend `initialData`
- [x] Backend `AGENTS.md` updated

Tests:
- [x] Health check still passes
- [x] `GET /api/board` and `PUT /api/board` without a session return 401
- [x] `GET /api/board` with a session returns the seeded board with 5 columns and 8 cards
- [x] `PUT /api/board` round-trips: rename, reorder, edit and delete, then read back and
      compare exactly
- [x] `PUT /api/board` rejects a dangling `cardIds` reference with 422 and stores nothing
- [x] `PUT /api/board` rejects malformed bodies with 422
- [x] Deleting the database file and reinitialising recreates it and reseeds
- [x] `initialise` is idempotent: repeated calls leave one user and one board
- [x] One user's board is never returned to another user, and one user's write does not
      change another's board
- [x] A session for a user with no board returns 404
- [x] A test proving the seed board has not drifted from the frontend's `initialData`

Verified against the running container by hand, not only in tests: a board change survived
a `docker compose restart`, a broken payload returned 422, and an unauthenticated request
returned 401.

Success criteria:
- [x] A fresh container with no database and no volume comes up with a working board
- [x] The suite passes with no network access
- [x] A board change survives a container restart

---

## Part 7: Frontend + Backend

The frontend uses the API, making this a persistent board.

Substeps:

- [x] `fetchBoard` and `saveBoard` added to `frontend/src/lib/api.ts`, relative URLs only
- [x] `frontend/src/hooks/useBoard.ts` owning load, debounced save, and error state
- [x] `KanbanBoard` reduced to a view over `useBoard`, with five pure `update` transforms
- [x] Load via `GET /api/board` on mount, with distinct loading and error states
- [x] Debounced ~500 ms whole-board `PUT /api/board`
- [x] Flush immediately with `keepalive: true` when the page is hidden
- [x] A save indicator in the header reading "All changes saved" / "Saving" / the error
- [x] A failed save is surfaced, not swallowed
- [x] `KanbanBoard.test.tsx` rewritten to drive the real fetch path
- [x] `App.test.tsx` updated to serve a board from its fetch stub
- [x] Playwright specs no longer depend on the seeded ids `card-card-1` and
      `column-col-review`; they select by position and read the card's testid from the DOM
- [x] Playwright set to `workers: 1`, because the suite shares one board and every save is
      a whole-board PUT
- [x] Update `frontend/AGENTS.md`

Tests:
- [x] RTL: the board renders data returned by a mocked `GET /api/board`
- [x] RTL: it renders data that differs from the built-in mock, proving the API is the source
- [x] RTL: a loading state shows before the board arrives
- [x] RTL: a failed load is reported rather than spinning forever
- [x] RTL: adding a card triggers a `PUT` containing the new card
- [x] RTL: renaming a column issues one `PUT`, not one per keystroke
- [x] RTL: a failed save surfaces an error
- [x] RTL: unsaved changes are flushed with `keepalive` when the page is hidden
- [x] RTL: loading the board does not trigger a write
- [x] Playwright: add a card, reload, the card is still there
- [x] Playwright: rename a column, reload, the name persists
- [x] Playwright: drag a card to another column, reload, it stays there

Two things the work surfaced:

- **A real invariant gap, found by hand rather than by a test.** A `PUT` that appended a
  card to a second column without removing it from the first was accepted, and the card
  rendered in two columns at once. Since any client that appends without removing can do
  this, `BoardData` now rejects a card appearing in more than one place, with two tests.
  Documented in `docs/DATA-MODEL.md` as driven by a real failure.
- **Whole-board saves mean concurrent tabs clobber each other.** Not fixed here, because
  the MVP has one user and one tab. Recorded as a known gap for Part 9, which does
  read-modify-write server-side and therefore needs a decision.

Verified by hand against the container: a rename, a card edit, and a card move all survived
a `docker compose restart`, and the board rendered from the API on the next sign-in.

Success criteria:
- [x] Changes survive a full page reload and a container restart
- [x] Renaming a column does not generate a request per character: proven by setting the
      debounce to 0, which turns one `PUT` into six for a five-character rename
- [x] `npm run test:unit` and `npm run test:e2e` both pass, in Docker

---

## Part 8: AI connectivity

The backend can call OpenRouter. Proved with a trivial prompt.

Substeps:

- [x] `ai.py` with an `AiClient` reading `OPENROUTER_API_KEY` from the environment
- [x] `GET /api/ai/ping` asking the model to answer `2+2`, returning the answer and model
- [x] The route requires a session, since it spends the API key
- [x] Typed failures: `AiNotConfigured` to 503, `AiUnavailable` to 502, never a traceback
- [x] A 30 s timeout and exactly one retry, skipped for 401/403 since a bad key stays bad
- [x] Log the model name and completion token count, never the key
- [x] `logging.basicConfig` in the lifespan, without which the usage line is dropped
- [x] `httpx2` promoted from a dev dependency to a runtime one
- [x] A `live` pytest marker, skipped unless `RUN_LIVE=1`
- [x] Backend `AGENTS.md` updated

Tests:
- [x] `GET /api/ai/ping` with a stubbed client returns 200 and the answer
- [x] The prompt really does ask the 2+2 question
- [x] The route requires a session
- [x] A missing key returns 503 naming the variable, not a stack trace
- [x] An upstream failure returns 502
- [x] The client raises before making any request when there is no key
- [x] The client retries once on a 5xx and then succeeds
- [x] The client gives up after the retry rather than looping
- [x] The client does **not** retry a 401, and the message names the key variable
- [x] An unexpected response shape becomes a clean failure, not a crash
- [x] The request carries the model name and a bearer token
- [x] The API key never appears in logs, and never in an error message
- [x] One `live` test asserting the real model answers 4

Three problems the work surfaced, none of which a mocked test would have caught:

- **`httpx2` was a dev dependency but `app/ai.py` imports it at runtime.** The app image
  installs with `--no-dev`, so the container crashed on startup with
  `ModuleNotFoundError: No module named 'httpx2'`. The host virtualenv had it, so the
  host suite passed throughout. Promoted to `dependencies`.
- **The OpenRouter usage line was never logged.** The root logger defaults to WARNING, so
  `logger.info` was dropped silently and nothing failed. Now configured in the lifespan.
- **The e2e suite was not idempotent.** Because the board is persistent, a second run
  found two cards titled "Survives a reload" and Playwright's strict mode failed the
  query. e2e now runs against its own `app-e2e` service with a tmpfs database, recreated
  before each run, so it never touches the real board either.

Verified: no unit test touches the network (the whole suite passes with all external HTTP
routed to a dead proxy), and the live test passes both on the host and in Docker.

Success criteria:
- [x] The live test passes against the real API and the key is never logged
- [x] No unit test touches the network
- [x] The endpoint answers through the running container, and `401` without a session

---

## Part 9: Board-aware AI

The AI receives the board JSON plus the message and history, and replies with structured
output containing a user-facing reply and a list of board operations.

Proposed operation schema, one object per change:

```json
{
  "reply": "Added the card to Backlog.",
  "operations": [
    { "op": "create_card", "column_id": "col-backlog", "title": "Fix login bug", "details": "..." },
    { "op": "move_card",   "card_id": "card-4", "column_id": "col-review" },
    { "op": "update_card", "card_id": "card-2", "title": "New title", "details": "..." },
    { "op": "delete_card", "card_id": "card-7" },
    { "op": "rename_column", "column_id": "col-discovery", "title": "Research" }
  ]
}
```

Substeps:

- [x] **Validated the schema against the live model first**, with six prompts per shape
      and three runs per ambiguous case. Recorded below.
- [x] `ops.py` with a discriminated union of five operations: `create_card`, `move_card`,
      `update_card`, `delete_card`, `rename_column`
- [x] `CHAT_RESPONSE_SCHEMA` derived from the pydantic models, not hand-written, so the
      schema sent to the model and the parser cannot drift
- [x] `apply_operations` applying each operation and collecting a warning per skip
- [x] `create_card` mints its id server-side; the model never chooses one
- [x] `chat.py` building the prompt: board JSON, valid column and card ids spelled out,
      the trimmed history, then the new message
- [x] `db.update_board` doing read, transform, and write in one transaction
- [x] `POST /api/chat` taking `{message, history}` and returning `{reply, board, warnings}`
- [x] `require_user` applied
- [x] `AiClient.complete_json` for structured output
- [x] Both `live` tests skip on a 429 rather than failing the suite
- [x] The model made configurable via `OPENROUTER_MODEL`, defaulting to the model this
      was validated against
- [x] `normalise_reply` recovering the operation when the model names the discriminator
      key differently
- [x] Backend `AGENTS.md` updated

### What the live probes found

Three schema shapes were tried against the real model, six prompts each, counting whether
returned ids actually exist:

| Shape | Valid ids |
|---|---|
| flat object, every field required, strict | 5/6, inventing `card_id` on create |
| discriminated union, strict | **11/12** |
| discriminated union, lenient | 10/12 |

The flat shape fails because strict mode requires a `card_id` on every operation, including
`create_card`, and the model invents one to fill it. The discriminated union has nowhere to
put that field, which is why it wins. Strict also beat lenient on semantics, not just ids.

The pydantic-derived schema then scored 6/6 on ids, so no hand-written schema is needed.

**The model is still wrong about one request in twelve.** Ids are reliable; intent is not.
One probe asked to move a card and got `create_card` back, which would create a card rather
than move one, and no id check catches that because both ids are valid. Recorded as a known
limit of a small free fine-tune rather than papered over. A retry on mismatched intent is
the next step if it proves too wrong in use.

The free tier also rate-limited hard enough that several live calls in a row returned 429,
which is why both `live` tests now skip on a 429.

### Switching model

The user chose `stealth/space-bunny-alpha` via `OPENROUTER_MODEL`, which surfaced a second
interop problem the original validation could not have found. That model returns correct,
fully schema-shaped replies, but names the operation discriminator key differently on
different calls: `op`, then `action`, then `operation`, for the same request. Every other
field, including all ids, was correct every time.

Left alone, every `create_card` was discarded with "the reply could not be read as a set of
board changes" while the model's own `reply` told the user the card had been added. The
worst kind of failure: confident and wrong.

`ops.normalise_reply` identifies the operation by its value, which is always one of the
five known names, instead of guessing a list of key names. It rewrites a reply only when
exactly one non-data field holds a known name, so a card genuinely titled `create_card` is
not mistaken for a discriminator, and an ambiguous reply is left alone to fail loudly.

After that, seven consecutive live calls covering all five operations and a no-op were
clean, and the board ended up in the expected state. `test_model_config.py` and the
`normalise_reply` tests both fail if the corresponding protection is removed.

Worth knowing: the schema validation in the table above was done against
`dots-studio/dots-3-note-preview:free`. A different model can behave differently, so the
probe is worth repeating when the model changes. That is now a documented step rather than
something to rediscover.

Tests:
- [x] `POST /api/chat` without a session returns 401
- [x] With no operations the board is unchanged and the reply is returned verbatim
- [x] A `create_card` adds to the end of the right column with a server-minted id
- [x] Two created cards get distinct ids
- [x] A `move_card` appends to the end of the target and removes it from the source
- [x] A `move_card` within one column reorders it
- [x] An `update_card` changes title and details and keeps position
- [x] A `delete_card` removes it from the map and from every `cardIds`
- [x] A `rename_column` changes only the title
- [x] Operations apply in the order given
- [x] An unknown `card_id` or `column_id` is skipped, the rest still apply, and a warning
      is returned
- [x] A board returned by `apply_operations` still satisfies every invariant
- [x] The change is persisted, so a following `GET /api/board` reflects it
- [x] The prompt carries the board JSON and the valid ids
- [x] The prompt asks for the chat response schema by name
- [x] The new message is the last message, after the system prompt and the history
- [x] History is trimmed to the most recent 20 messages
- [x] An unreadable reply leaves the board untouched and reports a warning
- [x] An upstream failure returns 502 and changes nothing
- [x] A malformed body returns 422
- [x] No table in the database can hold a transcript
- [x] One `live` test covering a real create, skipping if the provider is rate limiting

Success criteria:
- [x] The schema was validated against the real model before any application code
- [x] No operation can corrupt the board, whatever the model returns
- [x] The suite passes with the AI mocked and no network access

---

## Part 10: AI chat sidebar

A sidebar supporting full chat, wired to the backend, refreshing the board when the AI
changes it.

Substeps:

- [x] `Workspace` owning both the board and the chat, so one component is the single
      owner of state
- [x] `KanbanBoard` converted to a controlled view taking `board` and `onChange`, with an
      optional `sidebar` node rendered beside the grid
- [x] Board grid made responsive (`sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5`) since
      360 px of sidebar comes out of the width
- [x] `ChatSidebar` with a transcript, input, send control, and pending state
- [x] A "New chat" control clearing the transcript only, never the board
- [x] Conversation history in React state, trimmed to the most recent 20 messages
- [x] The empty state says a refresh starts a new conversation, so it does not read as a
      bug
- [x] `sendChat` added to the API client
- [x] `useBoard.replaceBoard` adopting the assistant's board **without** marking it dirty,
      since the backend already stored it
- [x] Warnings from skipped operations rendered under the reply
- [x] Input and send disabled while a request is in flight, with a pending indicator
- [x] `data-testid` hooks on the sidebar, transcript, warnings, and pending state
- [x] Update `frontend/AGENTS.md`

Tests:
- [x] RTL: the sidebar renders beside a board that still has its five columns
- [x] RTL: an empty state shows before anything is said
- [x] RTL: sending shows the reply and the user's own message
- [x] RTL: a reply containing changes updates the visible board with no reload
- [x] RTL: warnings from skipped operations are shown
- [x] RTL: the input and send button are disabled while a request is in flight
- [x] RTL: an empty or whitespace-only message is ignored
- [x] RTL: previous turns are sent as history without repeating the new message
- [x] RTL: history is trimmed to the most recent 20 messages
- [x] RTL: "New chat" empties the transcript and leaves the board untouched
- [x] RTL: a failed request is reported without breaking the board
- [x] RTL: adopting the assistant's board does not re-save it
- [x] Playwright: the sidebar is visible next to a five-column board
- [x] Playwright: a reply shows without a reload
- [x] Playwright: a reply updates the board with no reload
- [x] Playwright: warnings are shown
- [x] Playwright: "New chat" clears the conversation but keeps the board
- [x] Playwright: the input is disabled while a reply is in flight
- [x] Playwright: dragging still works after the chat has been used

### Model usage in tests

Per the user's instruction to keep model use low, the e2e suite makes **zero** OpenRouter
calls: `chat.spec.ts` stubs `POST /api/chat` in the browser, and the backend's two `live`
tests stay opt-in behind `RUN_LIVE=1` and skip on a 429. The only real model call made
during this part was one deliberate end-to-end check, plus the screenshot.

### Four real problems the e2e run exposed

- **`app-e2e` was serving a stale image.** It had its own compose service and therefore its
  own image tag, so rebuilding `app` left it running old code and the sidebar simply was
  not there. It now reuses the `pm-app` image, and `scripts/test.sh` builds it first. This
  is the second stale-image trap in this project, after the `httpx2` dev-dependency one.
- **The chat drag test could not see the board.** Filling the chat textarea scrolls it into
  view, which pushed the board above the fold, so `boundingBox()` returned `y = -145` and
  the mouse drag went nowhere. `measureForDrag` now scrolls to the top and both drag tests
  assert the boxes are on-screen.
- **A chat test corrupted the shared board.** The suite shares one seeded board, so saving
  the stub's two-column board left the next spec asserting against two columns instead of
  five. `chat.spec.ts` now absorbs `PUT /api/board`.
- **A test named a card after a button it looked for.** Cards have a `Delete <title>`
  button, so `/new chat/i` matched both that and the real button. The test now queries the
  exact accessible name, and transcript assertions are scoped to the transcript.

Success criteria:
- [x] A user can sign in, chat, and watch the board change without reloading
- [x] Manual drag and drop still works with the sidebar open
- [x] All unit and e2e suites pass
- [x] The e2e suite makes no model calls
- [x] Verified in a real browser against the real model, by screenshot

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The free model invents card or column ids | AI edits land on the wrong card or are rejected | Validate ids in `ops.py`; validate the schema against the live model at the start of Part 9 before building on it |
| Static export means the board HTML is served before the auth check resolves | Board markup briefly present to an unauthenticated user | Accepted for a local-only MVP; the API is still protected. Recorded decision, not an oversight |
| `next/font/google` fetches fonts at build time | Docker build fails without network | Build with network; if unavailable, switch to system fonts or self-hosted files |
| Per-keystroke column rename | One request per character | Debounced whole-board `PUT`, plus a flush on page hide |
| A whole-board `PUT` loses a concurrent change | Overwritten edits | Chat path uses a read-modify-write in one transaction; a last-write conflict strategy is documented if it bites |
| Renaming a column fires on every keystroke in the existing component | No commit boundary to attach persistence to | The debounce is the commit boundary; no component change required in Part 7 |
| Free-tier model rate limits or outages | Flaky live tests and a poor demo experience | Marked `live` tests are skipped by default; timeouts plus one bounded retry |
| The checkout path contains a colon, which breaks `uv run` and `npm ci` on the host | No host-side tooling works at all | All build and test commands run in Docker via `scripts/*.sh`. Proven by running the same commands on a colon-free copy, where they succeed. If the colon is ever removed, host commands work again; do not hardcode paths to work around it |
| A hand-rolled `FileResponse` path could serve files outside the static dir | Container filesystem disclosure | `is_relative_to` guard in the static handler, with a regression test that drives the ASGI app directly, since an HTTP client normalises `..` away before the request reaches the handler |

## Open questions

None blocking.

- Part 7: what the user sees if a save fails, exactly. Settled in Part 7 as
  "Could not save your changes. They may be lost if you close this tab."
- Part 9: conversation history persistence. **Settled by the user: browser only.** Recorded
  in the locked decisions table above.

Both chat decisions are now closed: history is React state only, lost on refresh, trimmed
to 20 messages on the way to the model. If losing the transcript on refresh turns out to be
annoying in use, the change is to mirror it in `localStorage`; nothing else moves.

## Known deltas from the plan (post-review)

A full code review (see `docs/code_review.md`) found these gaps between the plan and the
code, since addressed or explicitly accepted:

- Card editing was required by the brief but had no UI path. Fixed: every card now has
  an inline Edit form (`KanbanCard.tsx`) writing through the same save funnel.
- Concurrent writes were last-writer-wins. Fixed: `boards.revision` plus `If-Match` /
  `X-Board-Revision`, with 409 on conflict (see `docs/DATA-MODEL.md`).
- `frontend/AGENTS.md` and `backend/AGENTS.md` described earlier parts of the plan and
  contradicted the code in places. Both rewritten to match the current tree.
- `frontend/tests/chat.spec.ts` encodes the shared-board e2e invariant only in routing
  code; it is now commented as load-bearing in the spec itself.
- Accepted for the MVP: single hardcoded account (`user` / `password`), loopback-only
  port binding, and no board history (conflicts are detected, not rolled back).

Both MVP limitations above are lifted in Part 11.

---

## Part 11: Real accounts, multiple boards, due dates and labels

Part 11 lifts the two MVP limitations: one hardcoded user, one board per user. It adds
real registered accounts with hashed passwords, any number of boards per user, optional
due dates and labels on cards (also editable by the AI), and a pass of UI polish across
the whole app. It is recorded here because Parts 1-10 are history; the same conventions
apply: tests first, one part at a time, no box ticked without a passing test.

### Locked decisions for Part 11

| Area | Decision | Why |
|---|---|---|
| Password hashing | stdlib `hashlib.pbkdf2_hmac` (SHA-256, 240k iterations), stored as `pbkdf2_sha256$240000$salt$hash` | No new dependency; constant-time verify with `secrets.compare_digest`; a known algorithm written into the stored string so the cost can be raised later without a migration |
| Registration | `POST /api/register {username, password}`, signs the user in on success | One round trip; there is no admin concept in a local app |
| Existing demo user | Seeded with password `password` | Backwards compatible: the old hardcoded credential keeps working, but is now a real row with a real hash |
| Boards table | Rebuilt without `UNIQUE(user_id)`, gains `name TEXT NOT NULL` | The documented change in DATA-MODEL.md. Old databases are migrated on startup, keeping data and revisions |
| Board API | `GET /api/boards` (list), `POST /api/boards` (create), `PUT /api/boards/{id}` (rename), `DELETE /api/boards/{id}`, `GET/PUT /api/boards/{id}/board` (data) | The old `GET/PUT /api/board` routes remain as aliases for the user's first board during the transition, so any client not yet updated keeps working |
| Per-board chat | `POST /api/chat` gains `board_id` | The AI edits the board you are looking at |
| New-user seeding | A registration creates one board named "First board" with the standard five columns, empty of cards | The demo `user` keeps its seeded board; new accounts start with a clean structure |
| Due dates and labels | Optional `dueDate` (ISO date string) and `labels` (string list) on `Card`, in the JSON blob | No schema change; both flow through the same whole-board PUT contract; the AI's create/update ops accept them too |
| UI polish | Top bar with board switcher, keyboard drag support, focus rings, conflict banner with a Reload action | The impeccable pass: same tokens, same visual language, better states |

### Substeps

Backend:
- [x] `app/auth.py`: `hash_password`, `verify_password`, registration validation, `RegisterRequest`; remove the hardcoded constants
- [x] `db.py`: migrate `users` to have `password_hash`; migrate `boards` (drop the UNIQUE, add `name`); seed the demo user's hash and board on first run
- [x] `db.py`: `create_board`, `list_boards`, `rename_board`, `delete_board`, board-scoped `load_board_with_revision` / `save_board` / `update_board`
- [x] `main.py`: `POST /api/register`; `GET/POST /api/boards`, `PUT/DELETE /api/boards/{id}`, board-scoped data routes, `board_id` on the chat route
- [x] `models.py` / `ops.py`: optional `dueDate` and `labels` on `Card`, and on the AI's `create_card` / `update_card`

Frontend:
- [x] `api.ts`: register, board list/create/rename/delete, board-scoped load/save/chat
- [x] `LoginView`: Sign in / Create account tabs
- [x] `BoardSwitcher` in a top bar: list boards, create, rename, delete; Workspace loads the selected board and passes `boardId` to the chat
- [x] Card due dates and labels in the edit form, badges on the card and the drag preview
- [x] Polish: keyboard drag (`KeyboardSensor`), visible focus rings, conflict banner with Reload, refined empty/loading/error states, responsive top bar

E2E:
- [x] Rework the auth suite for register + login; board suite for multi-board (each spec creates its own board); keep the chat suite's PUT-absorption invariant under the new routes
- [x] Update `docs/DATA-MODEL.md`, both `AGENTS.md` files, and `README.md`

Tests: registration (success, duplicate, validation), password verification, migration of an old database (user hash + board rename + UNIQUE drop, keeping data and revision), board CRUD with per-user isolation, board-scoped revisions, due dates and labels round-tripping, AI ops with due dates and labels, chat scoped to the requested board, RTL for the switcher / register / due-date form, Playwright for register + multi-board + due dates.

### One deviation from the plan above

The switcher is named `TopBar.tsx` rather than a separate `BoardSwitcher` component. It is
one sticky header holding the switcher, the save status, and the sign-out button, and
splitting the switcher out would have meant threading the same props through two layers
for no gain.

### One defect the tests missed, and the fix

`UpdateCard` originally carried `due_date_set` and `labels_set` boolean fields to express
"absent means keep what is there". Nothing ever set them, so a model asking to change a
due date got a confident reply and an unchanged card. The tests passed because they
constructed `UpdateCard(..., due_date_set=True)` by hand, which skips the parse path where
the distinction is actually decided.

Fixed by deleting both fields and reading `operation.model_fields_set` in `_update_card`,
which pydantic already fills with exactly the keys the reply contained. That is smaller
than what it replaced, cannot be spoofed by the model, and keeps the two booleans out of
`CHAT_RESPONSE_SCHEMA`. The due-date tests now go through `ChatResponse.model_validate`;
`test_a_due_date_from_the_model_is_applied` and
`test_the_due_date_flags_are_not_part_of_the_wire_contract` both fail if the fields return.
Verified by reintroducing the bug: the first two fail.

Success criteria:
- [x] A visitor can register a real account and gets a clean five-column board
      (`test_registration_creates_a_user_and_signs_them_in`,
      `test_a_registered_user_gets_a_starter_board`, and the Playwright spec of the same name)
- [x] `user` / `password` still signs in and still sees its board
      (`test_an_old_database_is_migrated_keeping_data_and_revision` covers the backfill on an
      upgraded database; `test_first_run_seeds_a_five_column_board` covers a fresh one)
- [x] A user can create, rename, switch between, and delete boards, and one user's boards
      are never visible to another (`test_a_user_can_create_and_list_boards`,
      `test_a_board_can_be_renamed`, `test_a_board_can_be_deleted`,
      `test_another_users_board_is_invisible`, `test_deleting_another_users_board_is_refused`,
      plus the Playwright switcher specs)
- [x] Cards can carry a due date and labels, set by hand or by the AI, and both persist
      (by hand: Playwright "a card's due date and labels survive a reload"; by the AI:
      `test_a_due_date_from_the_model_is_applied`,
      `test_update_card_clears_a_due_date_only_when_asked`)
- [x] The full suite, build, lint, and typecheck pass, and the e2e run makes no model calls
- [ ] The running app, exercised in a real browser, is visibly more polished than before

Verified: 152 backend tests passed with 2 `live` tests skipped, 44 vitest, 25 Playwright,
`npm run lint` and `npx tsc --noEmit` both exit 0, and the e2e run makes no OpenRouter
call. `npx tsc --noEmit` used to report errors in the two oldest test files, which relied
on Vitest globals; they now import from `vitest` explicitly and the typecheck is clean.

The last criterion is unticked because "visibly more polished" is a judgement that needs a
human looking at the app, not something a passing test can assert.
