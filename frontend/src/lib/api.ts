import type { BoardData } from "@/lib/kanban";

export type SessionUser = { username: string };

// Relative URLs on purpose: FastAPI serves the page and the API from one origin, and
// the session cookie is scoped to that origin.
const jsonHeaders = { "Content-Type": "application/json" };

// The backend stamps every board read/write with a revision and bumps it on write.
// PUTs and chat turns send If-Match so a stale writer gets 409 instead of silently
// clobbering another writer's change.
const REVISION_HEADER = "X-Board-Revision";

export type BoardWithRevision = { board: BoardData; revision: number };

const revisionFrom = (response: Response): number => {
  const raw = response.headers.get(REVISION_HEADER);
  const revision = raw === null ? NaN : Number.parseInt(raw, 10);
  return Number.isNaN(revision) ? 0 : revision;
};

export class RevisionConflictError extends Error {
  constructor() {
    super("The board changed in another tab or chat turn. Reload to continue.");
    this.name = "RevisionConflictError";
  }
}

const throwConflict = (): never => {
  throw new RevisionConflictError();
};

export const fetchSession = async (): Promise<SessionUser | null> => {
  const response = await fetch("/api/me");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
  return (await response.json()) as SessionUser;
};

export const signIn = async (
  username: string,
  password: string
): Promise<SessionUser> => {
  const response = await fetch("/api/login", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 401) {
    throw new Error("Invalid username or password");
  }
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
  return (await response.json()) as SessionUser;
};

export const signOut = async (): Promise<void> => {
  const response = await fetch("/api/logout", { method: "POST" });
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
};

export type ChatWarning = string;

export type ChatTurn = {
  reply: string;
  board: BoardData;
  warnings: ChatWarning[];
  revision: number;
};

export const sendChat = async (
  message: string,
  history: { role: "user" | "assistant"; content: string }[],
  expectedRevision?: number
): Promise<ChatTurn> => {
  const headers: Record<string, string> = { ...jsonHeaders };
  if (expectedRevision !== undefined) {
    headers["If-Match"] = String(expectedRevision);
  }
  const response = await fetch("/api/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({ message, history }),
  });
  if (response.status === 409) {
    throwConflict();
  }
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
  const turn = (await response.json()) as ChatTurn;
  // Trust the header when present; older backends omit it.
  if (response.headers.get(REVISION_HEADER)) {
    turn.revision = revisionFrom(response);
  }
  return turn;
};

export const fetchBoard = async (): Promise<BoardWithRevision> => {
  const response = await fetch("/api/board");
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
  return {
    board: (await response.json()) as BoardData,
    revision: revisionFrom(response),
  };
};

// keepalive lets a save survive the page being unloaded, which is what the flush on
// page hide relies on. The payload is a single small board, far below the browser's
// 64 KB keepalive limit. If-Match makes a stale writer 409 rather than a silent clobber.
export const saveBoard = async (
  board: BoardData,
  expectedRevision?: number,
  keepalive = false
): Promise<void> => {
  const headers: Record<string, string> = { ...jsonHeaders };
  if (expectedRevision !== undefined) {
    headers["If-Match"] = String(expectedRevision);
  }
  const response = await fetch("/api/board", {
    method: "PUT",
    headers,
    body: JSON.stringify(board),
    keepalive,
  });
  if (response.status === 409) {
    throwConflict();
  }
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
};
