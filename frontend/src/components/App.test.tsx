import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "@/components/App";
import { initialData } from "@/lib/kanban";

// A minimal stand-in for Response. jsdom has no fetch, and the API client only uses
// status, ok, json(), and headers.get().
const stub = (status: number, body?: unknown) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => body,
  headers: { get: () => null },
});

const signedIn = { username: "user" };

// Routes every URL the app touches, so a test only states the auth outcome it cares
// about. The board is served because KanbanBoard fetches it once signed in.
type Routes = Partial<Record<string, (body?: unknown) => ReturnType<typeof stub>>>;

const setupFetch = (routes: Routes = {}) => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const route = routes[key];
    if (route) return route(body);
    if (key === "GET /api/board") return stub(200, initialData);
    if (key === "PUT /api/board") return stub(200, body);
    throw new Error(`unexpected call to ${key}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

describe("App session gate", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the login form and not the board when signed out", async () => {
    setupFetch({ "GET /api/me": () => stub(401) });

    render(<App />);

    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Kanban Studio" })).toBeNull();
  });

  it("shows the board when a session already exists", async () => {
    setupFetch({ "GET /api/me": () => stub(200, signedIn) });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Kanban Studio" })
    ).toBeInTheDocument();
    expect(screen.queryByTestId("login-form")).toBeNull();
  });

  it("does not render the board before the session check resolves", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve) => {
            resolveFetch = resolve;
          })
      )
    );

    render(<App />);

    // Still resolving: neither view may be shown yet.
    expect(screen.queryByTestId("login-form")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Kanban Studio" })).toBeNull();

    await act(async () => {
      resolveFetch(stub(401));
    });

    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
  });

  it("swaps to the board after a successful sign in", async () => {
    setupFetch({
      "GET /api/me": () => stub(401),
      "POST /api/login": () => stub(200, signedIn),
    });

    render(<App />);

    await userEvent.type(await screen.findByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("heading", { name: "Kanban Studio" })
    ).toBeInTheDocument();
    expect(screen.queryByTestId("login-form")).toBeNull();
  });

  it("shows an error and stays on the login form for bad credentials", async () => {
    setupFetch({
      "GET /api/me": () => stub(401),
      "POST /api/login": () => stub(401),
    });

    render(<App />);

    await userEvent.type(await screen.findByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByTestId("login-error")).toHaveTextContent(
      "Invalid username or password"
    );
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });

  it("returns to the login form after signing out", async () => {
    setupFetch({
      "GET /api/me": () => stub(200, signedIn),
      "POST /api/logout": () => stub(200, { ok: true }),
    });

    render(<App />);

    await userEvent.click(
      await screen.findByRole("button", { name: /sign out/i })
    );

    expect(await screen.findByTestId("login-form")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Kanban Studio" })).toBeNull();
    });
  });
});
