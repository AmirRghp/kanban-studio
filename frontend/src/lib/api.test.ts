import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RevisionConflictError,
  fetchBoard,
  fetchSession,
  saveBoard,
  sendChat,
} from "@/lib/api";

// A minimal stand-in for Response; the client reads status, ok, json, and headers.
// Header lookup is case-insensitive, as the real Headers.get is.
const stub = (
  status: number,
  body?: unknown,
  headers: Record<string, string> = {}
) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => body,
  headers: {
    get: (name: string) => {
      const lower = name.toLowerCase();
      const match = Object.entries(headers).find(
        ([key]) => key.toLowerCase() === lower
      );
      return match ? match[1] : null;
    },
  },
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fetchSession", () => {
  it("returns the user on 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => stub(200, { username: "user" }))
    );

    await expect(fetchSession()).resolves.toEqual({ username: "user" });
  });

  it("returns null on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(401)));

    await expect(fetchSession()).resolves.toBeNull();
  });

  it("throws on an unexpected status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(500)));

    await expect(fetchSession()).rejects.toThrow("Unexpected status 500");
  });
});

describe("fetchBoard", () => {
  it("returns the board and the revision header", async () => {
    const board = { columns: [], cards: {} };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => stub(200, board, { "X-Board-Revision": "7" }))
    );

    await expect(fetchBoard()).resolves.toEqual({ board, revision: 7 });
  });

  it("falls back to revision 0 when the header is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => stub(200, { columns: [], cards: {} }))
    );

    await expect(fetchBoard()).resolves.toMatchObject({ revision: 0 });
  });

  it("throws on a non-OK response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(404)));

    await expect(fetchBoard()).rejects.toThrow("Unexpected status 404");
  });
});

describe("saveBoard", () => {
  it("sends If-Match with the expected revision", async () => {
    const fetchMock = vi.fn(async () => stub(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    const board = { columns: [], cards: {} };

    await saveBoard(board, 4);

    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit & { headers: Record<string, string> }
    ];
    expect(init.method).toBe("PUT");
    expect(init.headers["If-Match"]).toBe("4");
    expect(init.keepalive).toBe(false);
  });

  it("passes keepalive through", async () => {
    const fetchMock = vi.fn(async () => stub(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await saveBoard({ columns: [], cards: {} }, 0, true);

    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit & { keepalive: boolean }
    ];
    expect(init.keepalive).toBe(true);
  });

  it("throws RevisionConflictError on 409", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(409)));

    await expect(saveBoard({ columns: [], cards: {} }, 1)).rejects.toBeInstanceOf(
      RevisionConflictError
    );
  });

  it("throws on other non-OK statuses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(500)));

    await expect(
      saveBoard({ columns: [], cards: {} }, 1)
    ).rejects.toThrow("Unexpected status 500");
  });
});

describe("sendChat", () => {
  it("posts the message and If-Match, and prefers the reply header", async () => {
    const fetchMock = vi.fn(async () =>
      stub(
        200,
        { reply: "ok", board: { columns: [], cards: {} }, warnings: [], revision: 99 },
        { "X-Board-Revision": "12" }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const history = [{ role: "user" as const, content: "first" }];

    const turn = await sendChat("hello", history, 11);

    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit & { headers: Record<string, string>; body: string }
    ];
    expect(init.headers["If-Match"]).toBe("11");
    expect(JSON.parse(init.body)).toEqual({ message: "hello", history });
    expect(turn.revision).toBe(12);
  });

  it("throws RevisionConflictError on 409", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => stub(409)));

    await expect(sendChat("hi", [])).rejects.toBeInstanceOf(RevisionConflictError);
  });
});
