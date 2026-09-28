# Frontend: Kanban Studio

Working Next.js MVP of the Kanban board. The board and chat talk to the FastAPI backend
on the same origin through `src/lib/api.ts`: session gating (`App.tsx`), board loading
and debounced whole-board saves (`useBoard.ts` with `If-Match` revision checks), the AI
chat (`Workspace.tsx` + `ChatSidebar.tsx`), and inline card editing (`KanbanCard.tsx`).
Only the chat transcript is client-only state; the board is persisted server-side.
Read this before changing anything here.

## Stack

| Concern | Choice | Version |
|---|---|---|
| Framework | Next.js App Router, React | 16.1.6 / 19.2.3 |
| Language | TypeScript, `strict: true` | 5.x |
| Styling | Tailwind CSS v4 (CSS-first config) | 4.1.18 |
| Drag and drop | `@dnd-kit/core` + `sortable` + `utilities` | 6.3.1 / 10.0.0 |
| Conditional classes | `clsx` | 2.1.1 |
| Unit tests | Vitest + Testing Library + jsdom | 3.2.4 |
| E2E tests | Playwright (chromium only) | 1.58.0 |

There is no `tailwind.config.*` file by design. The theme lives in `globals.css`.
There is no state library, no data-fetching library, and no HTTP client. Do not add one
without a reason; the plan calls for a thin fetch wrapper.

## Commands

**npm cannot run on this host.** The checkout path contains a colon
(`AI Coder: Vibe Coder to Agentic Engineer`) and `npm ci` fails part-way through with a
`napi-postinstall: not found` error while linking `node_modules/.bin`. This was confirmed
by running the identical `npm ci` on a copy at a colon-free path, where it succeeds. There
is no `node_modules` in the repo and there should not be one. All frontend work happens in
Docker, from the project root:

```bash
./scripts/test.sh                                        # every suite, in order

docker compose --profile test run --rm frontend-test     # vitest only
docker compose --profile test run --rm e2e                # playwright only
```

To iterate without rebuilding, bind-mount the source over the image copy:

```bash
docker compose --profile test run --rm \
  -v "$PWD/frontend/src:/build/src" frontend-test
```

For a shell, where `npm run dev`, `npm run build`, `npm run lint` and `npm run test:*` all
work normally:

```bash
docker compose --profile test run --rm frontend-test sh
```

## File map

```
src/
  app/
    layout.tsx        Root layout (server component). Loads Space_Grotesk as
                      --font-display and Manrope as --font-body via next/font/google.
                      Sets metadata title "Kanban Studio".
    page.tsx          The only route, "/". Server component; renders <KanbanBoard/>.
    globals.css       Design tokens (:root) + minimal base styles.
    favicon.ico
  lib/
    kanban.ts         Types, hardcoded initialData, the pure helpers moveCard and
                      createId, and labelStyle for label chip colours.
    kanban.test.ts    3 unit tests for moveCard.
    api.test.ts       12 unit tests for the fetch client (revisions, If-Match, 409).
    api.ts            Session (fetchSession, signIn, register, signOut), board CRUD
                      (listBoards, createBoard, renameBoard, deleteBoard), board-scoped
                      data (fetchBoard, saveBoard), and sendChat.
  hooks/
    useBoard.ts       Loads one board by id, debounces saves, flushes on page hide.
  components/
    App.tsx           "use client". The session gate. Renders LoginView or Workspace.
    LoginView.tsx     "use client". Sign in / Create account tabs over one form.
    Workspace.tsx     "use client". Owns the board list, the board AND the chat.
    TopBar.tsx        "use client". Sticky header: board switcher, save status, sign out.
    ChatSidebar.tsx   "use client". Transcript, input, New chat. Presentational.
    KanbanBoard.tsx   "use client". Controlled view over the board, plus the DndContext.
    KanbanColumn.tsx  Droppable column + SortableContext + inline rename input.
    KanbanCard.tsx    Sortable card. Inline edit form, due date, labels.
    KanbanCardPreview.tsx  Non-interactive clone rendered inside DragOverlay.
    NewCardForm.tsx   Collapsible title/details form.
    Workspace.test.tsx   9 RTL tests for loading, debounced saving, and save errors.
    ChatSidebar.test.tsx 14 RTL tests for the chat flow, with fetch stubbed.
    App.test.tsx      6 RTL tests for the session gate, with fetch stubbed.
  test/
    setup.ts          Single line: imports @testing-library/jest-dom.
    vitest.d.ts       Type references for vitest and jest-dom matchers.  tests/
  helpers.ts          signIn, waitForBoard, waitForSaved, measureForDrag, uniqueName.
  kanban.spec.ts      9 Playwright e2e tests, including multi-board and due dates.
  auth.spec.ts        9 Playwright e2e tests for sign in and registration.
  chat.spec.ts        7 Playwright e2e tests. Stubs the AI, so no model calls.

Unit tests also cover `src/lib/api.test.ts` (the fetch client: revision headers,
If-Match, 409 conflicts) and the card-edit flow in `ChatSidebar.test.tsx`.
```

Config: `next.config.ts` (`output: "export"`, `images.unoptimized`), `tsconfig.json`
(path alias `@/* -> ./src/*`), `vitest.config.ts` (mirrors the `@` alias, since Vitest
does not read tsconfig paths), `playwright.config.ts`, `eslint.config.mjs`,
`postcss.config.mjs`.

## Data model

Defined in `src/lib/kanban.ts`. The shape is normalized: columns hold an ordered list of
card ids, cards live in a keyed map.

```ts
export type Card = {
  id: string;
  title: string;
  details: string;
  dueDate?: string | null;   // ISO date string, absent or null when unset
  labels?: string[];         // empty or absent means none
};
export type Column = { id: string; title: string; cardIds: string[] };
export type BoardData = { columns: Column[]; cards: Record<string, Card> };
```

`dueDate` and `labels` are optional so a board written by an older client, or one seeded
before Part 11, still typechecks and renders. The backend treats absent and explicit
`null` identically: both mean unset.

`initialData` is a hardcoded board: 5 columns (`col-backlog`, `col-discovery`,
`col-progress`, `col-review`, `col-done`) and 8 cards (`card-1` .. `card-8`). Ids are
stable slugs, which is what makes the e2e tests possible.

`labelStyle(label)` hashes the label text to one of five chip styles, so the same label is
always the same colour on every card with no stored state. It is a pure function in
`kanban.ts`, not a component, so the board, the card, and the drag preview all agree.

There is deliberately no `position`, `userId`, `boardId`, or timestamp field. Order is
implied by array position. Board identity is a server-assigned integer carried on the
request, not a field inside `BoardData`.

## Component tree

```
page.tsx (RSC)
  └── App ("use client", session gate: checking -> LoginView | Workspace)
        ├── LoginView            when signed out (sign in / create account tabs)
        └── Workspace ("use client", owns boards + active board + chat)
              ├── TopBar (board switcher, save status, sign out)
              ├── KanbanBoard (controlled view)  -> KanbanColumn x N
              │     └── sidebar -> ChatSidebar (transcript, input, New chat)
              └── DndContext
                    ├── section.grid  -> KanbanColumn x N
                    │                      ├── inline <input> for the column title
                    │                      ├── SortableContext -> KanbanCard x N
                    │                      └── NewCardForm
                    └── DragOverlay -> KanbanCardPreview
```

`Workspace` renders `TopBar` itself rather than passing it down, because the switcher
needs the board list and the save status, which `Workspace` owns. The board body renders
either a status line (`data-testid="board-loading"`, which also carries the load error)
or `KanbanBoard`, so there is never a half-populated board.

`KanbanColumn` receives `cards` already resolved from ids by `KanbanBoard`, so the column
component never looks inside the `cards` map itself.

## State and the mutation seams

`Workspace` owns everything: the board list, which board is active, the board itself, and
the chat transcript. It calls `listBoards()` on mount, selects the first board, and
passes that id to `useBoard(boardId)`. Then it hands both halves down as props:

- `KanbanBoard` is a **controlled view**. It receives `board` and `onChange` and holds only
  `activeCardId` for the drag overlay. It never touches the network.
- `ChatSidebar` is **presentational**. It takes messages, pending state, error, and
  callbacks.
- `TopBar` is presentational too, and takes the board list plus the save status.

`activeBoardId` is the single piece of state that decides which board every write targets.
`sendChat` passes it as `board_id`, so the AI always edits the board on screen.

There are five board mutation points, all pure `onChange` transforms:

| Handler | Trigger | Notes |
|---|---|---|
| `handleDragStart` | drag begins | sets `activeCardId` only |
| `handleDragEnd` | drop | calls `moveCard(prev.columns, activeId, overId)`; no-ops if `!over` or ids are equal |
| `handleRenameColumn` | `onChange` of the column input | **fires on every keystroke** |
| `handleAddCard` | `NewCardForm` submit | generates the id client-side with `createId("card")`; falls back to `"No details yet."` for empty details |
| `handleUpdateCard` | card "Edit" button | inline title/details/**due date**/**labels** form in `KanbanCard`, saved through the same `onChange` funnel. An empty date field stores `null`, and labels are split on commas and trimmed, so an empty field stores `[]` |
| `handleDeleteCard` | card "Remove" button | removes from the map and filters the id out of `cardIds` |

Two consequences worth knowing:

- `handleRenameColumn` fires per keystroke, which is exactly why `useBoard` debounces at
  `SAVE_DEBOUNCE_MS`. Removing the debounce turns one PUT into one per character, and
  `renaming a column issues one PUT, not one per keystroke` fails if you do.
- `createId` still mints card ids in the browser and the server stores them verbatim.
  Deliberate, and documented in `docs/DATA-MODEL.md`.
- A card's due date and labels are edited in the same inline form as its title, so there is
  one save funnel rather than two. The form holds the date as a string and sends `null`
  when the field is empty, which the backend reads as "unset".

## Authentication

A static export has no server to route, so there is no `/login` page. `App` decides what
to render at `/`:

1. `checking` — `GET /api/me` is in flight. **Neither** the board nor the login form is
   rendered, or the board would flash for signed-out visitors.
2. `signed-out` — `LoginView`, which has two tabs over one form: "Sign in" and "Create
   account". Registration posts to `/api/register`, which signs the new user in, so both
   tabs end in the same place. The error text comes from the thrown `Error`'s message, so
   the backend's reason ("Username must be 3-30 characters.") reaches the user instead of a
   generic failure.
3. `signed-in` — `Workspace`, which renders the `TopBar` (including sign out) and the board.

The session lives in an HttpOnly cookie set by FastAPI, so there is no token in JS and
nothing to clear client-side. The auth, board, and chat calls all live in
`src/lib/api.ts`.

`Workspace` takes `username` and `onSignOut`. `KanbanBoard` takes an optional `sidebar`
node and never sees either.

## Drag and drop behaviour

A single `DndContext` with `collisionDetection={closestCorners}`, a `PointerSensor` with
`activationConstraint: { distance: 6 }`, and a `KeyboardSensor` added in Part 11. The
pointer distance is what stops a click on the card's Edit or Remove button from starting a
drag. There is no `onDragOver` and no `onDragCancel`. Column reordering is not implemented;
columns render in array order and only cards are sortable. The board grid is
`grid gap-6 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5`, with the sidebar beside it at
`2xl` and below it otherwise.

`moveCard(columns, activeId, overId)` in `src/lib/kanban.ts` is a hand-written pure
function rather than dnd-kit's `arrayMove`. It resolves each id to an owning column via
`findColumnId` (which accepts either a column id or a card id), then:

- same column, dropped on the column: the card moves to the end;
- same column, dropped on a card: spliced into that card's index;
- cross column, dropped on the column: removed from source, appended to target;
- cross column, dropped on a card: removed from source, inserted at the over-card index;
- unresolvable id or identical ids: returns `columns` unchanged.

It returns a new `Column[]` and never touches card content. It is pure and already
unit tested, so the backend should reuse the same semantics rather than reimplementing
ordering rules.

## Styling conventions

Brand colors are CSS custom properties in `:root` in `globals.css` and are consumed as
Tailwind arbitrary values, e.g. `text-[var(--navy-dark)]`,
`bg-[var(--secondary-purple)]`, `ring-2 ring-[var(--accent-yellow)]`,
`border-[var(--stroke)]`, `shadow-[var(--shadow)]`. Tokens:

| Token | Value | Used for |
|---|---|---|
| `--accent-yellow` | `#ecad0a` | accent lines, drop-target ring, column marker |
| `--primary-blue` | `#209dd7` | links, key sections, "Add a card" outline |
| `--secondary-purple` | `#753991` | submit buttons |
| `--navy-dark` | `#032147` | headings and body text |
| `--gray-text` | `#888888` | supporting text and labels |
| `--surface` / `--surface-strong` | `#f7f8fb` / `#ffffff` | page and card backgrounds |
| `--stroke` / `--shadow` | translucent navy | borders and elevation |

Only `--color-background` and `--color-foreground` are registered in `@theme inline`, so
`bg-surface` and friends do **not** exist. New UI must keep using the
`var(--token)` arbitrary-value form, or `@theme` has to be extended first.

Other conventions worth matching:

- Utility classes are written inline in JSX. There are no shared `ui/` primitives;
  card and column surface class strings are currently copy-pasted.
- `clsx` is used where classes are conditional (drop target, dragging state).
- Visual language: large radii (`rounded-2xl` to `rounded-[32px]`), frosted
  `backdrop-blur` header, uppercase micro-labels with wide `tracking-[0.2em]` to
  `tracking-[0.35em]`, and `font-display` for headings.

## Selectors the tests depend on

Reuse or update these together; changing one without the other breaks the suites.

- `data-testid={`column-${column.id}`}` on each column `<section>`
- `data-testid={`card-${card.id}`}` on each card `<article>`
- `aria-label="Column title"` on the column rename input
- `aria-label={`Delete ${card.title}`}` on each card's Remove button
- Buttons and placeholders: "Add a card", "Add card", "Cancel", "Remove", "Card title", "Details"
- The `h1` reads "Kanban Studio"
- `data-testid="login-form"` on the login form, `data-testid="login-error"` on its error
- The login inputs are labelled "Username" and "Password"; the submit button reads "Sign
  in" or "Create your account" depending on the tab
- The tablist is `aria-label="Authentication mode"`, tabs "Sign in" and "Create account"
- The sign-out button reads "Sign out" then the username, e.g. "Sign out (user)"
- `data-testid="board-switcher"` on the switcher button, `data-testid="board-menu"` on the
  open menu, `data-testid="confirm-delete-{id}"` on the second delete click
- `data-testid="board-loading"` on the loading/error line shown in place of the board
- `aria-label="New board name"` and `aria-label="Board name"` on the create and rename
  inputs; the board entries carry "N cards"
- The card edit form's fields are labelled "Card title", "Details", "Due date", "Labels"

  Use the `data-testid` for the error rather than `getByRole("alert")`. Next.js renders
  its own `__next-route-announcer__` element with `role="alert"`, so a role query matches
  two nodes and Playwright fails in strict mode.

## Testing setup

Unit tests are colocated in `src/**` (`*.test.ts`, `*.test.tsx`); Vitest excludes the
Playwright `tests/` directory so there is no collision. `globals: true` is on, but every
test file imports `describe`/`it`/`expect` from `vitest` explicitly so `tsc --noEmit`
stays clean.

E2E uses `testDir: ./tests` and has **no `webServer` block**. Since Part 3 there is no
`next dev` to start: the app is served by FastAPI, which must already be running.
`baseURL` comes from `BASE_URL`, defaulting to `http://127.0.0.1:8000`. The `e2e` compose
service sets `BASE_URL=http://app:8000` and waits for the `app` service to be healthy.

Current suites: 3 unit tests for `moveCard`, 12 for the API client (`api.test.ts`), 9
RTL tests for `Workspace` (board persistence), 14 RTL tests for the chat flow (including
the replaceBoard race and inline card editing), 6 RTL tests for the session gate, 9
Playwright board tests, 9 Playwright auth tests, 7 Playwright chat tests.

Each e2e spec creates its own board via `uniqueName` and deletes it afterwards, rather
than sharing the seeded one. That is what replaced the older shared-board convention: a
spec no longer has to absorb other specs' saves, and the auth, chat and board suites can
run in any order.

`npx tsc --noEmit` reports pre-existing errors in the two oldest test files, which rely on
Vitest globals that `tsconfig.json` does not wire up. `next build` does not typecheck test
files, so this does not affect the image build. New test files should import from `vitest`
explicitly, as `App.test.tsx` does.

Playwright runs with `workers: 1`. Every save is still a whole-board `PUT` against one
container and one SQLite file, and two workers renaming the same board would still
conflict. Each test now uses its own board, which removes cross-spec clobbering, but the
serial setting is kept because the cost of proving otherwise is not worth it for an MVP.

The e2e specs deliberately avoid seeded ids such as `card-card-1`: they pick the first
card of the first column and the last column by position, and read the card's
`data-testid` from the DOM, so they keep working if the seed data changes.

Three e2e details are load-bearing, and each was a real failure first:

- **`chat.spec.ts` stubs `POST /api/chat` in the browser.** The whole e2e suite therefore
  makes zero OpenRouter calls: fast, deterministic, and immune to rate limits. The real
  model is only exercised by the backend's `live` tests, which need `RUN_LIVE=1`.
- **`chat.spec.ts` still absorbs `PUT /api/boards/{id}/board`.** Even with per-test boards,
  the stub returns a two-column board, and letting that save through would leave the test's
  own board in a state its later assertions do not expect. Absorb it.
- **`measureForDrag` scrolls to the top before a coordinate drag, and both drag tests
  assert the boxes are on-screen.** Typing into the chat textarea scrolls it into view,
  which pushed the board above the fold so `boundingBox()` returned a negative `y` and
  `page.mouse` moved to nowhere.

The viewport is pinned to 1600x1000 so the `2xl` layout, the one with the sidebar beside
the board, is what gets tested.

One trap worth knowing: a card's delete button is labelled `Delete <card title>`, so
naming a test card after a button the test looks for makes a name query match twice. Query
buttons by exact accessible name, and scope transcript assertions to
`data-testid="chat-messages"`.

`test-results/.last-run.json` is committed and goes stale; it is harmless.

## Persistence

`useBoard(boardId)` owns everything about talking to one board's API. It re-runs whenever
`boardId` changes, which is how switching boards works:

- Loads on mount and on every `boardId` change. `board` is `null` until it arrives, and
  `Workspace` renders `error ?? "Loading your board..."` for that state, so a failed load
  says so instead of showing a spinner that never resolves.
- `update(fn)` takes a pure transform. It reads the current board from a ref rather than a
  closure, and never performs a side effect inside a `setState` updater, which React may
  call more than once.
- Saves are debounced by `SAVE_DEBOUNCE_MS` (500). The newest board is held in a ref and
  flushed by a single timer.
- Anything still unsaved when the tab is hidden is flushed immediately with
  `keepalive: true`, so it survives the page going away.
- `isSaving` and `error` drive the `data-testid="save-status"` line in the `TopBar`, which
  reads "All changes saved", "Saving", or the failure message.

That indicator is not decoration. The e2e persistence tests wait for "All changes saved"
before reloading, because reloading mid-debounce would race the in-flight PUT.

**Two rules exist because switching boards creates a race, and both are load-bearing.**

- **Leaving a board must not lose an edit.** The `boardId` effect flushes any pending save
  for the *outgoing* board before clearing state. Dropping the timer without flushing would
  discard the last half-second of typing.
- **A save in flight for the board you left must not report or overwrite the new one.**
  `savingFor` records which board a pending save belongs to. `persist` compares it after
  the await: a mismatch means the user has since switched, so the result (a bumped
  revision, an error, a 409) is discarded rather than applied to the board now on screen.
  Without the check, a slow save for board A would write board A's revision onto board B
  and the next write would 409 for no visible reason.

## The chat sidebar

`Workspace` holds the transcript in React state. Nothing about a conversation is stored
server-side or on disk, so a refresh or a closed tab starts a new conversation, which is
why the empty state says so rather than looking broken. The transcript is per-tab and
survives switching boards, since the AI's replies are plain text.

`handleSend` computes the history from the messages captured *before* the new one is
appended, so the new message travels as `message` and is not duplicated into the history.
History is trimmed to the last 20 messages on the way out, matching `HISTORY_LIMIT` in the
backend, so the request stays bounded whatever the backend does.

`sendChat` carries `activeBoardId` as `board_id`, so the AI edits the board on screen. The
backend resolves that id against the signed-in user and 404s on anyone else's, so this
is convenience, not the security boundary.

When a reply comes back, `replaceBoard` adopts the board the backend already stored. It
deliberately does **not** mark the board dirty: marking it dirty would `PUT` the board
straight back to the server for nothing. There is a test for that.

`KanbanBoard` takes an optional `sidebar` node and renders it beside the board, stacking
below it until `2xl`. The board grid is `sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5`,
so it stays readable with 360 px of sidebar taken out of the width.

## The board switcher

`TopBar` holds the switcher, and `Workspace` owns the state behind it. Five operations, all
server calls rather than local edits, because a board name is a database column:

- **Select** sets `activeBoardId`, which reloads the board through `useBoard`.
- **Create** posts the name, then appends the returned summary to the list. It does not
  select the new board, so creating one cannot silently discard what you were looking at.
- **Rename** posts the new name and patches the matching entry, keeping the selected board
  selected. A rename is a single request, not a debounced one, unlike a column title.
- **Delete** is two-step: the button becomes "Delete?" and only a second click deletes.
  Deleting the board you are viewing falls back to the first remaining one, and the
  backend's 404 for a board that is already gone is tolerated, so a double delete is not
  an error.
- The menu closes on an outside click, via a listener added only while it is open.

Card counts come from the backend with the list, so the switcher does not have to load
every board to show "8 cards".

## Build and serving

`next build` writes a fully static site to `out/`, which the Dockerfile copies into the
Python image at `/app/app/static`. FastAPI serves it; there is no Node process at runtime.

Consequences to keep in mind:

- **No server-side behaviour.** No route handlers, no server actions, no SSR, no
  middleware, no `next/image` optimisation. Anything dynamic must be a client component
  calling `/api` with relative URLs, since FastAPI serves both from one origin.
- **The board HTML is public.** `out/index.html` is served to anyone who requests `/`
  before any client-side auth check runs. The API is what is protected. Accepted for a
  local-only MVP; see the risks table in `docs/PLAN.md`.
- **`next/font/google` fetches at build time.** The Docker build needs network access. The
  fonts are then self-hosted from `out/_next/static/media`, so runtime needs none.
- Adding a route means adding it to the export; there is no dynamic routing, so anything
  beyond `/` is a client-side view or a 404 fallback served by FastAPI.

## Known gaps

These are absences, not bugs, and none of them are closed by a later part of
`docs/PLAN.md`.

- **Conflicts are detected, not merged.** A 409 leaves the local board visible and tells
  the user to reload, which loses their unsaved edits rather than reconciling them. Fine
  for one user and one tab; a real merge would need per-card versioning.
- **The AI is wrong roughly one time in twelve.** See the measured notes in
  `backend/AGENTS.md`. Ids are reliable, intent is not, and nothing in the frontend can
  detect a `create_card` that was meant to be a `move_card`.
- **Chat history is per-tab and lost on refresh.** Settled deliberately; see the locked
  decisions in `docs/PLAN.md`.
- **The board HTML is public.** Accepted for a local-only MVP; see the risks table in
  `docs/PLAN.md`.
- **The transcript is not board-aware.** Switching boards keeps the same transcript, so
  the model can be asked about a board that is no longer on screen. The `board_id` on the
  request keeps it editing the right board, but the prose in the history can be stale.
