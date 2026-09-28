# Kanban Studio

A Kanban board with an AI sidebar, served from a single Docker container.

## Requirements

Docker with Compose, and a `.env` file in the project root:

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | yes | Authenticates the AI calls. Never sent to the browser. |
| `OPENROUTER_MODEL` | no | Which OpenRouter model to use. Defaults to `dots-studio/dots-3-note-preview:free`. |
| `SESSION_SECRET` | no* | Signs the session cookie. The dev default is publicly known and logs a warning at startup; set this for anything reachable by others. |

\* Required in practice for anything beyond a private, loopback-only instance. The app
binds to `127.0.0.1` by default; see `docker-compose.yml` if you deliberately expose it.

To try a different model, set `OPENROUTER_MODEL` and restart. Nothing else changes, and no
code edit is needed. Confirm which model is live with `GET /api/ai/ping`, which returns it
as `model`.

## Run

```bash
./scripts/start.sh    # builds and serves on http://localhost:8000
./scripts/stop.sh     # stops the container
```

Sign in at <http://localhost:8000> with the demo account `user` / `password`, or use the
**Create account** tab to register your own. A new account gets one board called "First
board" with the five standard columns and no cards; the demo account keeps its seeded
board. Usernames are 3-30 characters, passwords at least 8, and passwords are stored as
PBKDF2-SHA256 hashes, never in the clear.

Each account can hold any number of boards. The switcher in the top bar creates, renames,
switches between, and deletes them, and one user's boards are never visible to another.

Logs: `docker compose logs -f app`

## Data

The SQLite database is created on first run at `/app/data/app.db` inside a named Docker
volume, so the board survives `docker compose down`. The volume belongs to the Compose
project name `pm-mvp` (pinned at the top of `docker-compose.yml`), so moving or renaming
this checkout does not orphan it. Delete the volume to start over:

```bash
docker compose down -v
```

Writes are guarded by a board revision: the frontend sends `If-Match` with the revision
it read, and a write from another tab or chat turn answers `409` instead of silently
clobbering. The browser shows a reload hint when that happens.

A database from before the accounts work is migrated on startup: the demo `user` row gets
its password hash backfilled, so `user` / `password` keeps working, and the boards table is
rebuilt to drop its one-board-per-user constraint, keeping every board and revision.

## Tests

```bash
./scripts/test.sh       # backend pytest, frontend vitest, then playwright e2e
./scripts/test-unit.sh  # the two unit suites only, for a fast inner loop
```

Everything runs in Docker. The host cannot run `npm` or `uv run`, because the checkout
path contains a colon and both tools parse colon-separated path lists. See
`frontend/AGENTS.md`.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app and tests, see `backend/AGENTS.md` |
| `frontend/` | Next.js app, see `frontend/AGENTS.md` |
| `scripts/` | `start.sh`, `stop.sh`, `test.sh` |
| `docs/` | `PLAN.md` and design documents |
