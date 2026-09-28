# Kanban Studio

## Business Requirements

This project is building a Project Management App. Key features:
- A user can register an account or sign in
- When signed in, the user sees a Kanban board representing their project
- A user can have any number of boards, and switch, create, rename and delete them
- The Kanban board has fixed columns that can be renamed
- The cards on the Kanban board can be moved with drag and drop, and edited
- A card can carry an optional due date and labels, set by hand or by the AI
- There is an AI chat feature in a sidebar; the AI is able to create / edit / move one or more cards

## Limitations

For the MVP, this will run locally (in a docker container), bound to loopback by default.

For the MVP, a board belongs to exactly one user. There is no sharing or membership.

For the MVP, passwords are hashed with the stdlib (`hashlib.pbkdf2_hmac`) rather than
argon2 or bcrypt, and the session secret defaults to a publicly known dev value.

## Technical Decisions

- NextJS frontend
- Python FastAPI backend, including serving the static NextJS site at /
- Everything packaged into a Docker container
- Use "uv" as the package manager for python in the Docker container
- Use OpenRouter for the AI calls. An OPENROUTER_API_KEY is in .env in the project root
- Default to the `dots-studio/dots-3-note-preview:free` model, overridable with
  `OPENROUTER_MODEL` in `.env` so a different model can be tried without a code change
- Use SQLLite local database for the database, creating a new db if it doesn't exist
- Start and Stop server scripts for Mac, PC, Linux in scripts/

## Current State

Parts 1-10 of `docs/PLAN.md` are complete. Part 11 is implemented and verified by the
test suites: real accounts with hashed passwords, any number of boards per user, a board
switcher, and card due dates and labels, all editable by hand or by the AI. The app
builds and runs as one Docker container, serves the statically exported Next.js frontend
from FastAPI on port 8000, and has a working sign-in flow, a persistent SQLite-backed
board, and a chat sidebar where the AI edits the selected board through validated
operations. All of it is in `./scripts/start.sh` and `./scripts/test.sh`.

Read these before changing anything:

- `docs/PLAN.md` - the parts, substeps, and success criteria
- `docs/DATA-MODEL.md` - how accounts and boards are stored
- `frontend/AGENTS.md`, `backend/AGENTS.md`, `scripts/AGENTS.md` - the code itself

Everything is built and tested in Docker, via `./scripts/start.sh` and `./scripts/test.sh`.
The host cannot run `npm` or `uv run` because this checkout path contains a colon.

## Color Scheme

- Accent Yellow: `#ecad0a` - accent lines, highlights
- Blue Primary: `#209dd7` - links, key sections
- Purple Secondary: `#753991` - submit buttons, important actions
- Dark Navy: `#032147` - main headings
- Gray Text: `#888888` - supporting text, labels

## Coding standards

1. Use latest versions of libraries and idiomatic approaches as of today
2. Keep it simple - NEVER over-engineer, ALWAYS simplify, NO unnecessary defensive programming. No extra features - focus on simplicity.
3. Be concise. Keep README minimal. IMPORTANT: no emojis ever
4. When hitting issues, always identify root cause before trying a fix. Do not guess. Prove with evidence, then fix the root cause.

## Working documentation

All documents for planning and executing this project will be in the docs/ directory.
Please review the docs/PLAN.md document before proceeding.