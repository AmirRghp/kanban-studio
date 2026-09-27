# Code review

Reviewed on 2026-09-27 against the working tree on `main` (`ae223d6`). Read-only review;
nothing but this file was changed.

## Baseline vs pending work

The last commit predates nearly all of the application. Tracked at `ae223d6` is a
scaffold: a plain KanbanBoard demo, an empty `backend/` (only `AGENTS.md` stubs), no
Docker, no README. Everything that matters is uncommitted: ~52 files, +6412/-162, split
into 11 modified files and 41 untracked ones. The untracked set includes the entire
backend (`backend/app/`, `backend/tests/`, `backend/pyproject.toml`, `backend/uv.lock`),
the entire runtime frontend (`src/components/App/Workspace/ChatSidebar/LoginView`,
`src/hooks/`, `src/lib/api.ts`, the RTL tests), `Dockerfile`, `docker-compose.yml`,
`.dockerignore`, `README.md`, all three scripts, `docs/DATA-MODEL.md`, and the e2e specs.
The modified files are secondary: `next.config.ts` (static export), `page.tsx` (session
gate), `playwright.config.ts` (BASE_URL, no webServer), `KanbanBoard.tsx` (sidebar prop,
grid), `kanban.spec.ts`, `KanbanBoard.test.tsx` (deleted, replaced by `Workspace.test.tsx`),
and the `AGENTS.md` files.

There is no CI anywhere - no workflow, no pre-commit, no lint gate. The only thing that
runs code is `scripts/test.sh` by hand.

Until this diff is committed, the repository contains none of the product, and the
duplicate `AGENTS.md` story documents a system that exists only in the working tree.

## Overall health

For an MVP this is in good shape. The big structural decisions are right: one origin,
one container, one JSON blob per board, a typed operation model between the AI and the
board, `BoardData` as the single validation point for every entry path, sessions signed
by middleware, and a clean `create_app` factory that makes the test suite pleasant. The
documentation is unusually honest about trade-offs. Tests cover the right seams (ASGI-level
traversal, forged and cross-signed cookies, per-user isolation, discriminator recovery,
seed drift against the frontend).

The findings below are dominated by three themes:

1. **Uncommitted work and self-contradicting documentation** are the highest-severity
   items, ahead of any code defect.
2. **Chat / board write races** in the frontend (stale-history, dirty-flag, and lost-PUT
   bugs) and a server-side last-writer-wins that the backend comments acknowledge but
   never mitigate.
3. **Build and toolchain fragility**: an unversioned compose project name that silently
   discards data, a `~=` npm caret pin that will break the e2e image against the lockfile,
   a minor-version requirement on a Python version that is being treated as a base image
   default, and no CI.

## Findings (high to low)

### 1. HIGH - The entire application is uncommitted

`git status` shows the whole product as untracked or modified (see baseline above). Any
`git checkout`, a reset by another agent or tool, or a fresh clone yields a repo with no
backend, no Docker, no scripts. There is also no branch hygiene: everything is one
unreviewable lump on `main` with no meaningful boundaries between parts (auth, board API,
chat, static serving are all interleaved).

**Impact:** total and silent loss risk; no code review history; nothing bisectable when a
regression appears.

**Action:** commit the work now in logical slices - (1) backend + tests, (2) Docker +
compose + scripts + README, (3) frontend app + tests, (4) docs and AGENTS updates. Keep
each slice buildable.

### 2. HIGH - Duplicate top-level AGENTS.md and backend/AGENTS.md contradict the code and each other

`AGENTS.md` (tracked, modified) and `backend/AGENTS.md` (untracked) are both
backend-oriented project specs. They disagree with the code and with each other:

- `AGENTS.md` says "the backend lives in backend/AGENTS.md" but describes no static file
  serving, no AI route, no board API; it predates Parts 5-10. `backend/AGENTS.md` describes
  them fully. Which one is authoritative is undefined.
- `backend/AGENTS.md` "Current state" opens mid-sentence ("Part 9. Static serving, sign-in,
  ...", line 40) with no heading before it. This is plausibly intentional shorthand for "as
  of Part 9" rather than a truncation, but a reader cannot tell the difference, and either
  way the section has no heading and the sentence reads broken.
- `backend/AGENTS.md` says `pydantic-settings` is "deliberately absent so far" and lists
  `pytest + httpx2 dev` deps, but `backend/pyproject.toml` has `pydantic-settings>=2.15.0`
  as a runtime dep and `httpx2` as runtime. Its own dependency table is stale.
- `backend/AGENTS.md` says "create_card never takes a card id from the model... because
  a model-chosen id either collides or fails the board's invariants", but the frontend
  `handleAddCard` mints ids client-side with `createId` (documented as deliberate in
  DATA-MODEL.md). The rationale sentence is wrong for the frontend path.

**Impact:** any contributor or agent following the wrong file writes code against the
wrong spec; the broken sentence hides the "Current state" heading it introduces.

**Action:** make root `AGENTS.md` a short pointer ("read backend/AGENTS.md, frontend/AGENTS.md,
scripts/AGENTS.md") plus the business requirements, and delete duplicated content. Fix the
truncated sentence in `backend/AGENTS.md` and correct the dependency and id-ownership notes.

### 3. HIGH - frontend/AGENTS.md is stale enough to mislead, and even claims the frontend makes no API calls

`frontend/AGENTS.md` (untracked, large, and the referenced authority for the frontend)
still describes Part 3:

- Opens with "It is a pure frontend demo: no API calls, no auth, no persistence", and the
  file map says `page.tsx` renders `<KanbanBoard/>`. All false: `api.ts` exists,
  `App.tsx` gates on a session, `page.tsx` renders `<App/>`.
- Claims the board grid is `lg:grid-cols-5`; it is now
  `sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5` (KanbanBoard.tsx:173).
- References a deleted `KanbanBoard.test.tsx` (3 tests) and says "KanbanBoard takes
  optional `onLogout` and `username` props" - the prop is `onSignOut` and the tests are
  `Workspace.test.tsx` (9), `ChatSidebar.test.tsx` (12), `App.test.tsx` (6).
- Lists component counts ("All 20 pass") that no longer match.

**Impact:** this is the file the project tells every contributor to read first; half of it
is a description of a version of the app that no longer exists.

**Action:** rewrite the "no API calls" opening, the file map, the component-tree section,
the test-count list, and the prop names in `frontend/AGENTS.md` to match the current tree;
keep only the still-true sections (drag behaviour, styling tokens, selector contract).

### 4. HIGH - Unversioned compose project name silently discards board data

`docker-compose.yml` sets no top-level `name:` and no `COMPOSE_PROJECT_NAME`. The project
name defaults to the checkout directory basename - here `AI Coder: Vibe Coder to Agentic
Engineer`, which normalizes to something like `ai_coder_vibe_coder_to_agentic_engineer`.
Moving or renaming the checkout (or running compose from a different path) creates a new
project with a fresh `app-data` volume. Because the database lives only in that named
volume (README "Data" section), the user's board silently vanishes and a new seed is
created; no error is shown.

**Impact:** guaranteed-seeming data loss on any path change; also two checkouts
accidentally share a volume if their normalized names collide.

**Action:** add a top-level `name:` (e.g. `pm-mvp`) to `docker-compose.yml` and note in the
README that the volume belongs to that project name.

### 5. HIGH - `@playwright/test` caret pin will break the e2e stage against the lockfile

`frontend/package.json` pins `"@playwright/test": "^1.58.0"` (caret), while
`frontend/package-lock.json` resolves `1.58.0`, and the e2e Docker stage hardcodes
`FROM mcr.microsoft.com/playwright:v1.58.0-noble` with a comment saying "The version here
must track the one in frontend/package.json". A caret pin does not track. `npm ci` is
lockfile-deterministic, so today's installs are safe; the risk is any lockfile
regeneration - adding a dependency, or an `npm install` that updates the lock - which
bumps the resolved version and leaves the e2e stage's fresh `npm ci` mismatched with the
pinned browser image. The well-known failure mode is `Executable doesn't exist ... please
run npx playwright install`, and running that inside the e2e stage is not how the image
is meant to be used.

**Impact:** the next lockfile regeneration can break the e2e suite with a confusing error,
in an environment (Docker) where the fix comment ("run npx playwright install") does not
apply.

**Action:** pin `"@playwright/test": "1.58.0"` exactly (drop the caret) in
`frontend/package.json`, and add a one-line check to `scripts/test.sh` or the Dockerfile
that fails the build when the lockfile version differs from the tag in the base image.

### 6. HIGH - `requires-python = ">=3.13"` lets a newer minor break the lockfile

`backend/pyproject.toml` sets `requires-python = ">=3.13"` while the app image uses
`python:3.13-slim` and the lock is resolved for 3.13. In a future image bump to
`python:3.14-slim` (or on a dev machine with 3.14), the lock is not re-resolved -
`uv sync --frozen` forbids that - but wheel *selection* from the lock happens per
interpreter, so a lock refresh or a 3.14 build can select the `cp314` wheels instead of
the `cp313` set that was actually tested (the lock carries both for pydantic-core, 30
`cp314` entries in total, which shows how real this is). The file itself documents the failure mode this causes:
annotations evaluated on a different interpreter version can turn into a FastAPI "missing
query parameter" error at runtime instead of an import error (comment above
`type Message` in `ai.py`).

**Impact:** a silent drift between what the lock pins and what production runs; reproducible
builds are the whole reason `uv.lock` is committed.

**Action:** use an upper bound: `requires-python = ">=3.13,<3.14"`. This is the same
convention the frontend uses implicitly by pinning Node in the base image (`node:24-alpine`).

### 7. MEDIUM - Chat turn loses manual edits: `replaceBoard` clears a pending debounce

`frontend/src/hooks/useBoard.ts:109` `replaceBoard` sets `current.current = next` and
`setBoard(next)` but does not touch `unsaved.current` or the pending timer, and the board
handlers stay live while a chat is in flight (`isPending` disables only the chat input).
Realistic sequence: the user sends a chat message -> while the reply is in flight (seconds,
not milliseconds) they rename a column, which sets `unsaved.current` and schedules a PUT ->
the reply lands and calls `replaceBoard` -> the pending timer then fires and `flush()` PUTs
`unsaved.current`, the pre-chat board, clobbering the chat-written board. A narrower
variant: an edit in the 500 ms before sending leaves the same pending PUT firing after
the reply. The backend does a read-modify-write inside `update_board`'s transaction, so
the AI's change is applied to the *current* stored board, but the browser then overwrites
it with a stale snapshot.

**Impact:** an edit made during or just before a chat turn silently reverts the
assistant's change.

**Action:** in `replaceBoard`, cancel any pending timer and clear `unsaved.current` (the
chat board is authoritative because the backend already stored it). One small guard:
if `unsaved.current` exists and differs from the fetched board when `replaceBoard` is
called, prefer flushing first and then adopting the chat board - or simply document and
disable the chat input while a save is pending.

### 8. MEDIUM - Chat history omits the just-answered board and assistant warnings; stale context is sent after an AI edit

`frontend/src/components/Workspace.tsx:37` computes `history = toHistory(messages)` from
the messages *before* the new user message is appended (correct for not duplicating the
message), but the assistant reply from the previous turn is the only record of what the AI
did - and `ChatMessage.warnings` and the board changes are not part of what gets sent.
More importantly, `backend/app/chat.py` rebuilds the system prompt from a fresh
`load_board` on every turn, which is right, but the *history* the backend receives can
describe a board that no longer exists: `ChatSidebar` renders `message.text` ("Added it.")
while the board has since been renamed/moved manually, so the model reconciles stale
transcript claims against a current board with no marker of when each claim was made. This
is inherent to "transcript in the browser" and is mitigated by re-sending ids each turn,
but the failure mode is undocumented.

**Impact:** multi-turn edits are more likely to invent ids or re-apply stale intent; the
project already documents "the model is still wrong roughly one time in twelve", and this
adds a systematic source of error on the most common second-turn case.

**Action:** document the limitation in `backend/AGENTS.md`, and consider sending the
applied-op summary (op names + ids) as part of each assistant history entry instead of
just the prose reply, so the model sees what actually changed rather than what it said.

### 9. MEDIUM - Server-side last-writer-wins between two browser tabs and between chat and PUT

`backend/app/db.py:159` `save_board` does an unconditional `UPDATE boards SET data = ?`,
and the backend comments (frontend/AGENTS.md "Known gaps", DATA-MODEL.md "Board
snapshots") acknowledge no revision counter. Two signed-in tabs (or a chat turn and a
manual save) clobber each other with no detection. The backend AGENTS.md says "a chat
cannot interleave with a manual save and clobber it" - that is true only for the duration
of `update_board`'s transaction, not across requests; the manual save after the chat still
reverts the chat's change.

**Impact:** silent data loss in a two-tab scenario, and cross-request clobbering between
chat and manual save, both undocumented as being *unfixed* rather than *fixed*.

**Action:** the minimal fix that fits the existing model: add an `updated_at` integer
revision to the `boards` row, return it from `GET /api/board`, and have `PUT /api/board`
take an `If-Match`-style expected revision, returning 409 when it does not match. The
frontend already has a single save funnel (`useBoard.persist`) to attach it to. If that is
too much for the MVP, at minimum correct the over-strong claim in `backend/AGENTS.md`.

### 10. MEDIUM - No CI of any kind

There is no `.github/workflows/`, no pre-commit hooks, no lint step in `scripts/test.sh`
(`npm run lint` exists in `frontend/package.json` and is never run by any script), and no
typecheck step (`npx tsc --noEmit` is known to fail on two older test files per
frontend/AGENTS.md, so the repo has no answer for type regressions either). The only
verification is a developer remembering to run `./scripts/test.sh` in Docker.

**Impact:** nothing prevents a broken commit; the caret-pin bug in finding 5 is
characteristically a CI-shaped failure.

**Action:** add a minimal GitHub Actions workflow that runs `./scripts/test.sh` on push
(Docker is already the test harness, so the runner only needs Docker) plus `npm run lint`
and `npm run build` in a `node:24` container. Fix or quarantine the two known tsc failures
first so the typecheck step is green.

### 11. MEDIUM - `GET /api/ai/ping` has no abuse control and the chat route has no rate limit

Both `POST /api/chat` and `GET /api/ai/ping` spend the OpenRouter API key and are guarded
only by `require_user`, which any visitor can satisfy with the public `user`/`password`
pair (hardcoded in `backend/app/auth.py:8-9` and published in the README). There is no
per-session or per-IP throttle; the free tier's own rate limit is the only backstop, and
`ai.py` retries once on 5xx/timeout, so a loop of failed pings makes 2 upstream calls each.

**Impact:** anyone on the local network (the compose file binds `0.0.0.0:8000`) can burn
the API key's quota, and the well-known credentials are printed in the README next to the
command to run it.

**Action:** for the MVP, state the threat model in the README ("binds on all interfaces;
anyone on the LAN gets the published credentials and your OpenRouter quota") and add a
bind-address option to compose, or move to `127.0.0.1:8000:8000`. A simple in-memory
per-session token bucket on the two AI routes is the smallest durable fix.

### 12. MEDIUM - `serve_static` 404s for real directories and returns 200 HTML for API-shaped misses after redirect

`backend/app/main.py:157-172` `serve_static` resolves `(static_dir / full_path)` and
checks `is_relative_to` before serving; traversal is covered and tested. Two smaller
issues:

- A request for an existing *directory* path (e.g. `/_next/static`) falls through to
  `FileResponse(index)` with 200, which is the SPA fallback and fine, but a request for a
  file inside the static dir with a `..` that stays inside (e.g. `/x/../index.html`) also
  resolves and serves - harmless, but it means the guard is doing double duty as a
  normalizer and there is no test that a *relative-internal* traversal stays inside.
- More substantively, `FileResponse(index)` is returned for **any** method-agnostic
  missing path with status 200 and `text/html`, including paths like
  `/api/board.cacheBuster` that bypass the `unknown_api_route` catch-all only because that
  route matches everything under `/api/`. The catch-all (`main.py:145`) is what protects
  the API namespace; it must stay registered before the mount, which is documented, but
  nothing fails if it is reordered - it is convention-enforced only.

**Impact:** low today; becomes a real bug the moment someone adds a route or moves the
catch-all.

**Action:** add a test that fails if the catch-all is moved after the static mount (e.g.
assert `GET /api/definitely-not-a-route` returns JSON `404` and not HTML 200 - the test
exists as `test_unknown_api_path_returns_404`, so just add an ordering assertion comment
and a second case with a `.json`-suffixed path). Optionally return 404 instead of index
for paths that look like files (contain a dot and no matching static file).

### 13. MEDIUM - Card edit does not exist in the UI, but the backend, tests, and docs all assume it

`AGENTS.md` business requirements say cards "can be moved with drag and drop, and edited".
There is no edit path in the frontend: `KanbanCard.tsx` has only `onDelete`, and a
`grep` for `onEdit|handleEdit|editing` across `frontend/src/components/` finds nothing.
The backend implements `update_card` (ops.py), the prompt documents it (chat.py
SYSTEM_RULES), `test_ops.py` covers it, and frontend/AGENTS.md's mutation-seams table
implies a rename-only surface. Editing a card is possible only through the AI.

**Impact:** a core stated requirement is unimplemented; users must go through the AI (and
spend quota) to fix a typo.

**Action:** either add an inline edit affordance to `KanbanCard` (a small `onUpdate` prop
wired to a `details`/`title` toggle, mirroring `NewCardForm`), or change `AGENTS.md` to
say editing is AI-only for the MVP. Doing nothing is the worst option because the docs
already promise it.

### 14. MEDIUM - `session_secret` falls back to an insecure default in a network-exposed container

`backend/app/config.py:23` defaults `session_secret` to `"dev-insecure-secret-change-me"`,
and `docker-compose.yml` re-supplies the same string via `${SESSION_SECRET:-dev-insecure-secret-change-me}`.
The comments are exemplary about *why*, but the failure mode is that a user who follows the
README (which never mentions `SESSION_SECRET`) is running a forgeable-cookie app bound to
`0.0.0.0` with well-known credentials - i.e. anyone on the LAN can mint a session for
`user`. `test_a_session_signed_with_another_secret_is_rejected` proves the mechanism works;
nothing detects the default in production.

**Impact:** combined with finding 11, a LAN attacker gets full board write access.

**Action:** make the compose default empty (`${SESSION_SECRET:-}`) and have `create_app`
log a single warning (not fail - this is a local MVP) when the secret is unset or equals
the known-dev value. One warning line is enough; do not add a validation framework.

### 15. LOW - `ai.py` builds a new `httpx2.Client` per attempt and per call

`backend/app/ai.py:107` opens a fresh client inside `_attempt` for every request; with
`MAX_ATTEMPTS = 2`, a retried chat costs two TCP+TLS handshakes to `openrouter.ai`. The
`AiClient` holds no other state, so a single client stored on the instance (created lazily,
closed never - process lifetime is fine) would amortize the handshake. The transport
injection point (`transport=`) already makes this test-friendly.

**Impact:** negligible latency per call for a human-driven chat, but it is the single
hottest code path and the fix is three lines.

**Action:** create the client once in `AiClient.__init__` (keeping the `transport`
parameter), use it for all attempts, and drop the `with` block. Keep `MockTransport`
injection as-is.

### 16. LOW - The chat route logs the raw model reply, and the chat prompt embeds the entire board JSON in every system message

`backend/app/chat.py:91` (in `run_chat`, not `complete_json`) logs `Raw reply: %s` on
validation failure. This is intentional
for diagnosability and does not contain the API key (guarded by
`test_the_api_key_is_never_logged` at the client level, not the chat level), but the raw
reply can include anything the model echoed back from the prompt - which includes the full
board content - at INFO/WARNING level in container logs. Separately, `build_messages`
embeds `board.model_dump_json()` into the system prompt on every turn; for a large board
this dominates token usage, and nothing bounds it (the frontend bounds only *history*).

**Impact:** mild log-privacy concern plus unbounded token growth on a free-tier model.

**Action:** truncate the raw reply in the log (`reply[:400]`), and add a short comment on
`build_messages` acknowledging that prompt size scales with board size, or cap the dumped
board with a warning comment if it exceeds a chosen size. Neither needs a test.

### 17. LOW - `Message` type is too loose; role and content are unvalidated

`backend/app/ai.py:25` declares `type Message = dict[str, str]`, and `ChatRequest.history`
accepts any list of string-to-string dicts, so `{"" : "hi"}` or `{"foo": "bar"}` passes
validation and is forwarded verbatim to OpenRouter as a message. `build_messages` also
accepts role values other than `user`/`assistant` from the client, letting a caller inject
a `system` message into the middle of the transcript.

**Impact:** low (single-user MVP, the only caller is our own frontend), but a user-role
injection in the middle of the history can contradict the system rules and is trivially
reachable with curl.

**Action:** replace `Message` with a small pydantic model (`role: Literal["user", "assistant"]`,
`content: str`) in `ChatRequest` and pass `.model_dump()` into the prompt builder. This
keeps the type honest and closes the injection in one move; `test_chat.py` already posts
history dicts and will exercise it.

### 18. LOW - `unknown_api_route` shadows a genuinely useful future route space and `include_in_schema=False` hides it

`backend/app/main.py:145` catches *every* `/api/*` path not matched earlier. Correct today,
but it also swallows typos for routes that will be added later (e.g. `/api/boards` for
multi-board support would 404 with "Not Found" until explicitly registered - that is the
desired failure mode, fine) *and* it returns `None` with a bare `HTTPException`, which is
correct, but `include_in_schema=False` on both the catch-all and the static mount means
the OpenAPI schema is not a complete picture of the server's routes. No `/openapi.json`
consumer exists today.

**Impact:** cosmetic; only matters if docs or tooling start consuming the schema.

**Action:** leave as-is; note in `backend/AGENTS.md` route-order section that the schema
is intentionally incomplete.

### 19. LOW - `docker-compose.yml` `e2e` service has no `image:`/`container_name` and test.sh never tears down

`scripts/test.sh` leaves `app-e2e` running after the suite (the comment says "leaves it
running afterwards", by design) but never removes the throwaway containers from
`run --rm` retries or stops `app-e2e` on failure. Repeated failed runs accumulate exited
containers and networks under the default project name. `e2e` builds its own image with
`npx playwright test` as CMD and no explicit image tag, so `docker compose build` outputs
three untagged images that `docker image prune` must clean up.

**Impact:** disk and container clutter over repeated runs; confusing `docker ps` output
after a failed suite.

**Action:** add `docker compose --profile test down --remove-orphans` at the end of
`scripts/test.sh` (and on `EXIT` via a trap, so failures clean up too), while keeping the
app service running if that is intended. Give the `e2e` service an explicit `image:` name.

### 20. LOW - `test.sh` ordering hides backend failures behind an expensive e2e run

`scripts/test.sh` runs backend, then frontend unit, then a full `docker compose build app`
plus e2e. Any backend failure already aborts (set -euo pipefail), which is right, but a
frontend unit failure still costs a full image build only to be discovered *after* the
backend suite - fine - while an e2e failure provides no artifact cleanup. More important
than ordering: `docker compose build app` inside `test.sh` is unconditional even when
nothing frontend-related changed, and Docker layer caching makes that cheap only when
`frontend/` is unchanged; a one-character README change still invalidates the
`COPY frontend/` layer and forces a full `next build`.

**Impact:** slow feedback loop for a small test change.

**Action:** leave the order (it is already cheapest-first); consider
`docker compose build --pull=false app` and a comment that frontend edits require the
rebuild, or split a `test:unit` script that skips the e2e half for inner-loop use.

### 21. LOW - Test suite asserts implementation details of Starlette cookie format

`backend/tests/test_board.py:20` `cookie_for` hand-builds a session cookie with
`itsdangerous.TimestampSigner` and a base64 payload, coupling the test to
Starlette's `SessionMiddleware` internals (the file comments this honestly). If
Starlette changes its payload framing, these isolation tests break for a reason unrelated
to the code under test.

**Impact:** test maintenance cost on a dependency upgrade; no correctness risk.

**Action:** acceptable as-is given the comment; if it ever breaks, prefer logging in as
the second user through the real endpoint (requires adding second-user credentials to
`auth.py`) rather than extending the cookie forgery.

### 22. LOW - `docs/PLAN.md` claims part completion that includes claims contradicted by `AGENTS.md`

`docs/PLAN.md` (modified, ~682 added lines) says all ten parts are complete, and
`AGENTS.md` "Current State" repeats it. Given findings 13 (no card edit) and the frontend
AGENTS drift, the "complete" claim is doing work that a reader should not trust without
checking. This is not a doc-formatting nit: the plan is the project's source of truth for
what exists.

**Impact:** anyone planning work on top of "all ten parts complete" inherits wrong
assumptions.

**Action:** add a short "Known deltas from the plan" section to `docs/PLAN.md` listing the
unimplemented requirement (card editing) and any other deltas found when this review's
actions are addressed.

### 23. LOW - `.dockerignore` does not exclude `docs/`, `.freebuff/`, or e2e artifacts from the build context

`.dockerignore` excludes node_modules, .next, out, test-results, .venv, __pycache__,
pytest_cache, pyc, .git, and .env. `docs/`, `frontend/tests/`, `test-results/` at other
paths, `.freebuff/`, and `.playwright-mcp`-style artifacts still land in the build context
sent for every build. The context is small today, so this is a hygiene note, not a
performance problem. Notably `.freebuff/` contains an internal project id that needlessly
ships into every `docker build` invocation's context (it is not copied into images, only
sent to the daemon).

**Impact:** trivial today; matters if the repo grows or if context contents ever leak into
a layer via a broad `COPY`.

**Action:** append `docs/`, `**/tests`, `.freebuff/`, and `*.md` to `.dockerignore` -
except the two `AGENTS.md` files if you want them available in images for debugging; the
Dockerfile only `COPY`s specific paths, so exclusion is safe.

### 24. LOW - Frontend `createId` collision risk is acknowledged nowhere it matters

`frontend/src/lib/kanban.ts:164` mints ids from `Math.random().toString(36).slice(2, 8)` +
base36 timestamp. Within one browser session, two cards created in the same millisecond
can collide only if `Math.random()` also collides in 6 characters (~2 billion space);
practically negligible, and `docs/DATA-MODEL.md` already says server-side ids are the fix
if uniqueness ever matters. But the backend applies `create_card` with its *own* uuid, so
a client-side collision can only ever affect a stale local board, not storage. No action
needed beyond the existing doc note.

**Impact:** none in practice.

**Action:** none required; optionally add the one-line caveat to `frontend/AGENTS.md` next
to `createId`.

### 25. LOW - `Workspace.test.tsx` and `ChatSidebar.test.tsx` stub `fetch` with an incomplete Response shape

The `stub` helper returns only `{status, ok, json}`; `sendChat` in `api.ts` also reads
`response.json()` only, so it works - but `signOut` in `api.ts` checks `response.ok` after
a POST that `App.test.tsx` stubs with `{status: 200, ok: true, json: async () => ...}`,
fine - while `saveBoard` with `keepalive` is never asserted to actually pass keepalive
through in any unit test (the visibility-flush test asserts `puts[0].keepalive` is true,
which does cover it). The real gap: no unit test covers `sendChat`'s non-OK path (the
`catch` branch in `Workspace.handleSend` that sets "The assistant could not be reached")
- that branch is exercised only in e2e (`reports a failed request`), which is fine, and no
unit test covers `fetchSession`'s non-401 non-OK path. Coverage is skewed toward the happy
path in `api.ts` precisely because the component tests stub fetch at the component level
rather than testing `api.ts` directly.

**Impact:** low; `api.ts` has no direct unit tests at all and relies on consumers to
exercise it.

**Action:** add a small `frontend/src/lib/api.test.ts` with three cases: 401 -> null for
`fetchSession`, non-OK -> throws for `saveBoard`, and 200 -> parsed board for `fetchBoard`.
This also gives a place for the keepalive pass-through assertion that currently lives
indirectly in a component test.

### 26. LOW - The e2e chat suite encodes a shared-board invariant that lives only in test code

`frontend/tests/chat.spec.ts` stubs `POST /api/chat` in the browser (sound - the suite
makes no model calls), and its `beforeEach` also absorbs `PUT /api/board`, because a chat
test that saved its stubbed two-column board would leave later specs asserting against two
columns instead of five. The invariant this encodes - the e2e board is shared across the
file, so a stub must never let a save through - is enforced only by routing code scoped to
this one file. `frontend/AGENTS.md` mentions the absorption once, in the same stale file
finding 3 flags, and nothing else documents or enforces it.

**Impact:** a future spec that stubs the board without absorbing the PUT silently poisons
every later test in the suite, with the failure surfacing far from the cause.

**Action:** state the shared-board rule and the PUT-absorption requirement as a
load-bearing convention where it can be found (a comment on the stub in `chat.spec.ts`
and a line in the e2e notes that survives the finding 3 rewrite), or give each spec its
own board and delete the invariant.

### 27. LOW - `next/font/google` makes the frontend build depend on network access to Google Fonts

`frontend/src/app/layout.tsx:2` loads `Space_Grotesk` and `Manrope` via
`next/font/google`, which fetches the fonts at `next build` time inside the
`frontend-build` Docker stage. `frontend/AGENTS.md` documents the build-time fetch, but
not its consequence for the CI this review recommends (finding 10): a hermetic or
proxy-restricted build environment fails the frontend build, and the error points at a
font fetch rather than at anything the developer changed.

**Impact:** an offline or restricted CI runner cannot produce the `app` image; a Google
Fonts outage breaks the build.

**Action:** none for local use - the fonts are self-hosted from `out/_next/static/media`
after the build, so runtime needs no network. When CI lands, either accept the network
requirement in the runner or switch both fonts to `next/font/local` with vendored files.

## Non-findings (checked and fine)

For reviewers who want to know what was looked at and *not* flagged:

- **Path traversal**: the `is_relative_to` check plus the ASGI-level test driving raw
  paths is correct and well tested, including the fact that a normal HTTP client
  normalizes `..` before the request leaves it (test_static.py docstring).
- **SQL injection**: all queries are parameterized; `executescript(SCHEMA)` is a constant.
- **API key handling**: key never logged or returned; `test_the_api_key_is_never_logged`
  and `test_the_api_key_is_never_in_an_error_message` cover it; compose reads it at
  runtime via `env_file`, never baked into a layer; `.dockerignore` excludes `.env`
  (caveat: `.env` itself could not be read during this review, so only the README's
  required-key contract was verified, not the file's actual contents).
- **Session forgery**: signed-cookie mechanism tested for forged, cross-signed, and
  wrong-secret cases.
- **Per-user isolation**: `boards.user_id` scoping is enforced in every query; the
  cross-user PUT test proves it.
- **Board invariants**: dangling refs, key/id mismatch, and duplicate placement are all
  model-level and tested.
- **Blocking I/O**: board routes are sync `def` (threadpool) as documented; `sqlite3`
  connections are opened and closed per operation, which is fine at this scale.
- **AI client error mapping**: 401/403 no-retry, 5xx/timeout one retry, malformed JSON and
  non-dict JSON both mapped to `AiUnavailable`; the discriminator recovery logic is
  genuinely careful and well tested, including the ambiguity guard.
- **Frontend debounced saves**: the ref-based `update` avoids stale closures and
  setState-updater side effects; visibilitychange flush with keepalive is correct.
- **Docker layering**: frontend deps stage is correctly split from the build stage so
  `npm ci` is cached; the `app-e2e` reuses the `app` image deliberately with a documented
  stale-image rationale.
- **Playwright config**: serial workers with an honest comment about why; BASE_URL
  override; viewport pinned for the 2xl layout.
