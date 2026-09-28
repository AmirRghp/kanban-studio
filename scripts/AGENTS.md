# Scripts

Start, stop, and test scripts for macOS, Linux, and Windows (via Git Bash or WSL). All
three are thin wrappers around Docker Compose; there is no host-mode path.

| Script | Does |
|---|---|
| `start.sh` | Checks `.env` exists, then `docker compose up --build -d --wait` |
| `stop.sh` | `docker compose down` |
| `test.sh` | Checks the Playwright lock/image match, runs all suites, cleans up on exit |
| `test-unit.sh` | Backend + frontend unit suites only, no e2e or app image build |

All three resolve the project root from their own location, so they work from any
directory. The app is served on <http://localhost:8000> once started.

Logs: `docker compose logs -f app`.

`.github/workflows/ci.yml` runs `test.sh` on every push to `main` and every pull request,
plus `npm run lint` and `npx tsc --noEmit` on a `node:24` runner. The suite job needs
nothing but Docker, since `test.sh` is Docker-only anyway. Keep that workflow in step with
`test.sh`: a suite added to one and not the other means CI silently stops checking it.

The test suites are Docker-only by necessity, not preference. The host cannot run `npm`
or `uv run`, because the checkout path contains a colon and both tools parse
colon-separated path lists. See `frontend/AGENTS.md`.

`e2e` depends on `app` being healthy, so `test.sh` starts the app if it is not already
running and leaves it running afterwards. Use `stop.sh` to shut it down.
