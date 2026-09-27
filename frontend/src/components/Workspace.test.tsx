import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Workspace } from "@/components/Workspace";
import { initialData } from "@/lib/kanban";

// A minimal stand-in for Response. jsdom has no fetch, and the API client only uses
// status, ok, json(), and headers.get().
const stub = (status: number, body?: unknown) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => body,
  headers: { get: () => null },
});

type PutCall = { board: Record<string, unknown>; keepalive: boolean };

const setupFetch = (
  overrides: {
    get?: () => ReturnType<typeof stub>;
    put?: (body: unknown) => ReturnType<typeof stub>;
  } = {}
) => {
  const puts: PutCall[] = [];

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/board" && (!init || init.method === undefined)) {
      return overrides.get ? overrides.get() : stub(200, initialData);
    }
    if (url === "/api/board" && init?.method === "PUT") {
      const board = JSON.parse(String(init.body));
      puts.push({ board, keepalive: Boolean(init.keepalive) });
      return overrides.put ? overrides.put(board) : stub(200, board);
    }
    throw new Error(`unexpected call to ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, puts };
};

const putCalls = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "PUT"
  );

// The board and its persistence live in Workspace now, so that is what the board tests
// drive. Rendering Workspace keeps their original intent: real data flow, real saving.
const renderBoard = async () => {
  render(<Workspace username="user" onSignOut={() => {}} />);
  return screen.findByRole("heading", { name: "Kanban Studio" });
};

describe("board persistence", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the board returned by the API", async () => {
    setupFetch();
    await renderBoard();

    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
    expect(screen.getByText("Align roadmap themes")).toBeInTheDocument();
  });

  it("renders data that differs from the built-in mock", async () => {
    setupFetch({
      get: () =>
        stub(200, {
          columns: [
            { id: "c1", title: "Only Column", cardIds: ["k1"] },
            { id: "c2", title: "Empty", cardIds: [] },
          ],
          cards: { k1: { id: "k1", title: "From The Server", details: "d" } },
        }),
    });
    await renderBoard();

    expect(screen.getAllByTestId(/column-/i)).toHaveLength(2);
    expect(screen.getByText("From The Server")).toBeInTheDocument();
    expect(screen.queryByText("Align roadmap themes")).toBeNull();
  });

  it("shows a loading state before the board arrives", () => {
    setupFetch();
    render(<Workspace username="user" onSignOut={() => {}} />);

    expect(screen.getByText("Loading your board...")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kanban Studio" })).toBeNull();
  });

  it("surfaces a failure to load", async () => {
    setupFetch({ get: () => stub(500) });
    render(<Workspace username="user" onSignOut={() => {}} />);

    await waitFor(() => {
      expect(screen.getByTestId("save-status")).toHaveTextContent(
        "Could not load your board."
      );
    });
  });

  it("adds a card and sends it in a PUT", async () => {
    const { puts } = setupFetch();
    await renderBoard();

    const column = screen.getAllByTestId(/column-/i)[0];
    await userEvent.click(within(column).getByRole("button", { name: /add a card/i }));
    await userEvent.type(
      within(column).getByPlaceholderText(/card title/i),
      "Persisted card"
    );
    await userEvent.type(within(column).getByPlaceholderText(/details/i), "notes");
    await userEvent.click(within(column).getByRole("button", { name: /add card/i }));

    expect(within(column).getByText("Persisted card")).toBeInTheDocument();

    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 3000 });
    const sent = puts[0].board.columns as { id: string; cardIds: string[] }[];
    const sentCards = puts[0].board.cards as Record<string, { title: string }>;
    const newId = Object.keys(sentCards).find(
      (id) => sentCards[id].title === "Persisted card"
    );
    expect(newId).toBeDefined();
    expect(sent[0].cardIds).toContain(newId);
  });

  it("renaming a column issues one PUT, not one per keystroke", async () => {
    const { fetchMock, puts } = setupFetch();
    await renderBoard();

    const input = within(screen.getAllByTestId(/column-/i)[0]).getByLabelText(
      "Column title"
    );
    await userEvent.clear(input);
    await userEvent.type(input, "Inbox");

    // Nothing goes out while the user is still typing.
    expect(putCalls(fetchMock)).toHaveLength(0);

    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 3000 });
    const sent = puts[0].board.columns as { title: string }[];
    expect(sent[0].title).toBe("Inbox");
  });

  it("reports a save failure instead of failing silently", async () => {
    setupFetch({ put: () => stub(500) });
    await renderBoard();

    const input = within(screen.getAllByTestId(/column-/i)[0]).getByLabelText(
      "Column title"
    );
    await userEvent.clear(input);
    await userEvent.type(input, "Doomed");

    await waitFor(
      () => {
        expect(screen.getByTestId("save-status")).toHaveTextContent(
          "Could not save your changes"
        );
      },
      { timeout: 3000 }
    );
  });

  it("flushes unsaved changes when the page is hidden", async () => {
    const { fetchMock, puts } = setupFetch();
    await renderBoard();

    const input = within(screen.getAllByTestId(/column-/i)[0]).getByLabelText(
      "Column title"
    );
    await userEvent.clear(input);
    await userEvent.type(input, "Hidden");

    expect(putCalls(fetchMock)).toHaveLength(0);

    // jsdom keeps visibilityState at "visible", so the handler would ignore the event.
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].keepalive).toBe(true);
  });

  it("does not PUT on load", async () => {
    const { puts } = setupFetch();
    await renderBoard();

    // Reading the board must not trigger a write.
    expect(puts).toHaveLength(0);
  });
});
