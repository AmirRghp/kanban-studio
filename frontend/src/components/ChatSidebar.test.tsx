import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Workspace } from "@/components/Workspace";
import { initialData, type BoardData } from "@/lib/kanban";

const stub = (status: number, body?: unknown) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => body,
  headers: { get: () => null },
});

type ChatTurn = { reply: string; board: BoardData; warnings: string[] };

const boardWith = (title: string): BoardData => ({
  ...initialData,
  cards: {
    ...initialData.cards,
    "card-new": { id: "card-new", title, details: "from the assistant" },
  },
  columns: initialData.columns.map((column, index) =>
    index === 0
      ? { ...column, cardIds: [...column.cardIds, "card-new"] }
      : column
  ),
});

const setup = (
  options: {
    chat?: () => Promise<ReturnType<typeof stub>> | ReturnType<typeof stub>;
    board?: BoardData;
  } = {}
) => {
  const chatBodies: { message: string; history: unknown[]; board_id: number }[] = [];

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/boards") {
      return stub(200, [{ id: 1, name: "First board", cardCount: 8 }]);
    }
    if (url === "/api/boards/1/board" && (!init || init.method === undefined)) {
      return stub(200, options.board ?? initialData);
    }
    if (url === "/api/boards/1/board" && init?.method === "PUT") {
      return stub(200, JSON.parse(String(init.body)));
    }
    if (url === "/api/chat") {
      const body = JSON.parse(String(init?.body ?? "{}"));
      chatBodies.push(body);
      if (options.chat) return options.chat();
      return stub(200, {
        reply: "Added it.",
        board: options.board ?? initialData,
        warnings: [],
      } satisfies ChatTurn);
    }
    throw new Error(`unexpected call to ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, chatBodies };
};

const renderWorkspace = async () => {
  render(<Workspace username="user" onSignOut={() => {}} />);
  await screen.findByRole("heading", { name: "Kanban Studio" });
  await screen.findByTestId("chat-sidebar");
  return screen.getByTestId("chat-sidebar");
};

// The stubbed reply is the same every turn, so wait on the count rather than the text.
const waitForTurns = (count: number) =>
  waitFor(() => {
    expect(screen.getAllByText("Added it.")).toHaveLength(count);
  });

const send = async (text: string) => {
  await userEvent.type(screen.getByLabelText("Message"), text);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
};

describe("chat sidebar", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders beside a board that still has its five columns", async () => {
    setup();
    await renderWorkspace();

    expect(screen.getByTestId("chat-sidebar")).toBeInTheDocument();
    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
  });

  it("shows an empty state before anything is said", async () => {
    setup();
    await renderWorkspace();

    expect(screen.getByText(/No conversation yet/i)).toBeInTheDocument();
  });

  it("sends a message and shows the reply", async () => {
    const { chatBodies } = setup();
    await renderWorkspace();

    await send("Add a card called Fix login bug");

    expect(chatBodies).toHaveLength(1);
    expect(chatBodies[0].message).toBe("Add a card called Fix login bug");
    expect(await screen.findByText("Added it.")).toBeInTheDocument();
    expect(screen.getByText("Add a card called Fix login bug")).toBeInTheDocument();
  });

  it("updates the visible board from the response, with no reload", async () => {
    setup({
      chat: () =>
        stub(200, {
          reply: "Added a card.",
          board: boardWith("Card from AI"),
          warnings: [],
        }),
    });
    await renderWorkspace();

    expect(screen.queryByText("Card from AI")).toBeNull();
    await send("add a card");

    expect(await screen.findByText("Card from AI")).toBeInTheDocument();
  });

  it("shows warnings for operations that could not be applied", async () => {
    setup({
      chat: () =>
        stub(200, {
          reply: "Partly done.",
          board: initialData,
          warnings: ["skipped: no card with id 'card-99'"],
        }),
    });
    await renderWorkspace();

    await send("move something");

    const warnings = await screen.findByTestId("chat-warnings");
    expect(within(warnings).getByText(/card-99/)).toBeInTheDocument();
  });

  it("disables the input and send button while a request is in flight", async () => {
    let release: (value: unknown) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === "/api/boards") {
          return stub(200, [{ id: 1, name: "First board", cardCount: 8 }]);
        }
        if (url === "/api/boards/1/board" && (!init || init.method === undefined)) {
          return stub(200, initialData);
        }
        if (url === "/api/chat") {
          return new Promise((resolve) => {
            release = resolve;
          });
        }
        return stub(200, initialData);
      })
    );
    render(<Workspace username="user" onSignOut={() => {}} />);
    await screen.findByRole("heading", { name: "Kanban Studio" });
    await screen.findByTestId("board-grid");

    await send("slow request");

    expect(screen.getByTestId("chat-pending")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Message"), "");
    release(stub(200, { reply: "done", board: initialData, warnings: [] }));
    await screen.findByText("done");
    expect(screen.queryByTestId("chat-pending")).toBeNull();
  });

  it("ignores an empty message", async () => {
    const { chatBodies } = setup();
    await renderWorkspace();

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Message"), "   ");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(chatBodies).toHaveLength(0);
  });

  it("sends the previous turns as history, without repeating the new message", async () => {
    const { chatBodies } = setup();
    await renderWorkspace();

    await send("first");
    await waitForTurns(1);
    await send("second");

    expect(chatBodies).toHaveLength(2);
    expect(chatBodies[0].history).toEqual([]);
    expect(chatBodies[1].history).toEqual([
      { role: "user", content: "first" },
      { role: "assistant", content: "Added it." },
    ]);
  });

  it("trims history to the most recent 20 messages", async () => {
    const { chatBodies } = setup();
    await renderWorkspace();

    for (let i = 0; i < 12; i++) {
      await send(`m${i}`);
      await waitForTurns(i + 1);
    }

    const history = chatBodies[chatBodies.length - 1].history as {
      role: string;
      content: string;
    }[];
    // History is built before the new message is appended, so the 12th turn sends 22
    // messages and the oldest 2 are dropped. The oldest kept is m1.
    expect(history).toHaveLength(20);
    expect(history[0]).toEqual({ role: "user", content: "m1" });
    expect(history.some((m) => m.content === "m0")).toBe(false);
    expect(history[history.length - 1]).toEqual({
      role: "assistant",
      content: "Added it.",
    });
  });

  it("New chat empties the conversation but leaves the board alone", async () => {
    setup({
      chat: () =>
        stub(200, {
          reply: "Added a card.",
          board: boardWith("Card kept after reset"),
          warnings: [],
        }),
    });
    await renderWorkspace();
    await send("add a card");
    await screen.findByText("Card kept after reset");

    await userEvent.click(screen.getByRole("button", { name: "New chat" }));

    expect(screen.getByText(/No conversation yet/i)).toBeInTheDocument();
    expect(screen.queryByText("Added a card.")).toBeNull();
    // The board is untouched by starting a new conversation.
    expect(screen.getByText("Card kept after reset")).toBeInTheDocument();
    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
  });

  it("reports a failed request without breaking the board", async () => {
    setup({ chat: () => stub(502) });
    await renderWorkspace();

    await send("do something");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The assistant could not be reached"
    );
    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
  });

  it("does not re-save the board when the assistant returns it", async () => {
    const { fetchMock } = setup({
      chat: () =>
        stub(200, {
          reply: "Added a card.",
          board: boardWith("No extra save"),
          warnings: [],
        }),
    });
    await renderWorkspace();

    await send("add a card");
    await screen.findByText("No extra save");

    // The backend already stored that board, so the client must not PUT it back.
    const puts = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT"
    );
    await waitFor(() => {
      expect(puts).toHaveLength(0);
    });
  });

  it("does not PUT a stale snapshot after a chat turn (replaceBoard race)", async () => {
    // The finding-7 regression: an edit made while a chat turn is in flight must not
    // flush after replaceBoard adopts the assistant's board, which would clobber it.
    const { fetchMock } = setup({
      chat: () =>
        new Promise((resolve) => setTimeout(
          () =>
            resolve(
              stub(200, {
                reply: "Added a card.",
                board: boardWith("Board from chat"),
                warnings: [],
              })
            ),
          300
        )),
    });
    await renderWorkspace();

    await userEvent.type(screen.getByLabelText("Message"), "add a card");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    // Edit lands while the request is in flight; the debounce would fire at 500 ms.
    const input = within(screen.getAllByTestId(/column-/i)[0]).getByLabelText(
      "Column title"
    );
    await userEvent.clear(input);
    await userEvent.type(input, "Typed during flight");

    // The chat reply adopts its board and must cancel the pending flush.
    await screen.findByText("Board from chat");
    await waitFor(
      () => {
        expect(screen.getByTestId("save-status")).toHaveTextContent(
          "All changes saved"
        );
      },
      { timeout: 2000 }
    );
    // The debounced flush would have fired by now if replaceBoard had not cancelled it.
    const puts = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "PUT"
    );
    expect(puts).toHaveLength(0);
  });

  it("edits a card inline and sends the change in a PUT", async () => {
    const { fetchMock } = setup();
    await renderWorkspace();

    const column = screen.getAllByTestId(/column-/i)[0];
    const card = within(column).getAllByTestId(/card-/i)[0];
    await userEvent.click(within(card).getByRole("button", { name: /^edit /i }));

    const titleInput = within(card).getByLabelText("Card title");
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Edited title");
    await userEvent.click(within(card).getByRole("button", { name: "Save" }));

    expect(within(card).getByText("Edited title")).toBeInTheDocument();

    await waitFor(
      () => {
        const puts = fetchMock.mock.calls.filter(
          ([, init]) => (init as RequestInit | undefined)?.method === "PUT"
        );
        expect(puts).toHaveLength(1);
        const sentCards = (puts[0][1] as RequestInit & { body: string }).body;
        expect(sentCards).toContain("Edited title");
      },
      { timeout: 3000 }
    );
  });
});
