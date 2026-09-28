import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchBoard,
  saveBoard,
  RevisionConflictError,
  type BoardWithRevision,
} from "@/lib/api";
import type { BoardData } from "@/lib/kanban";

// A column rename fires on every keystroke, so writes are coalesced. Typing "Inbox"
// issues one PUT, not six.
export const SAVE_DEBOUNCE_MS = 500;

type BoardController = {
  board: BoardData | null;
  isSaving: boolean;
  error: string | null;
  update: (change: (current: BoardData) => BoardData) => void;
  replaceBoard: (next: BoardData, revision?: number) => void;
  getRevision: () => number;
};

export const useBoard = (boardId: number | null): BoardController => {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The ref is the source of truth for computing the next board, so `update` never
  // reads a stale closure and never performs a side effect inside a setState updater,
  // which React may call more than once.
  const current = useRef<BoardData | null>(null);
  const unsaved = useRef<BoardData | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The server's revision for the board in `current`. Sent as If-Match on writes so a
  // stale writer gets a 409 instead of silently clobbering another writer's change.
  const revision = useRef(0);
  // Which board the pending save belongs to. Switching boards cancels the flush, and
  // the id check keeps a slow in-flight save from writing board A's data to board B.
  const savingFor = useRef<number | null>(null);

  const clearPending = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    unsaved.current = null;
  }, []);

  const persist = useCallback(
    async (
      forBoardId: number,
      snapshot: BoardData,
      expectedRevision: number,
      keepalive: boolean
    ) => {
      setIsSaving(true);
      try {
        await saveBoard(forBoardId, snapshot, expectedRevision, keepalive);
        if (savingFor.current === forBoardId) {
          revision.current = expectedRevision + 1;
          setError(null);
        }
      } catch (caught) {
        if (savingFor.current !== forBoardId) {
          // The user switched boards; the save concerned a board they left.
          return;
        }
        if (caught instanceof RevisionConflictError) {
          // Another writer (second tab or a chat turn) got there first. The local
          // board stays visible; the user is told to reload rather than silently
          // overwriting or being overwritten.
          setError(
            "This board changed in another tab or chat. Reload to pick up the latest version."
          );
        } else {
          setError(
            "Could not save your changes. They may be lost if you close this tab."
          );
        }
      } finally {
        setIsSaving(false);
      }
    },
    []
  );

  const flush = useCallback(
    (keepalive = false) => {
      if (timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
      }
      const snapshot = unsaved.current;
      if (!snapshot || savingFor.current === null) return;
      unsaved.current = null;
      void persist(savingFor.current, snapshot, revision.current, keepalive);
    },
    [persist]
  );

  useEffect(() => {
    if (boardId === null) {
      setBoard(null);
      setError(null);
      return;
    }
    let cancelled = false;

    // Leaving a board must not discard unsaved edits: fire any pending save for the
    // outgoing board first (fire-and-forget; the guard inside persist already keys
    // error reporting to the board being left), then drop the old state.
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (unsaved.current && savingFor.current !== null) {
      const outgoing = savingFor.current;
      const snapshot = unsaved.current;
      unsaved.current = null;
      void persist(outgoing, snapshot, revision.current, false);
    }
    current.current = null;
    setBoard(null);
    setError(null);
    savingFor.current = boardId;

    fetchBoard(boardId)
      .then((loaded: BoardWithRevision) => {
        if (cancelled) return;
        current.current = loaded.board;
        revision.current = loaded.revision;
        setBoard(loaded.board);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this board.");
      });

    return () => {
      cancelled = true;
    };
  }, [boardId, persist]);

  // Anything still unsaved when the tab is hidden would otherwise be lost, since the
  // debounce may not have fired yet.
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") flush(true);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [flush]);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const update = useCallback(
    (change: (current: BoardData) => BoardData) => {
      const existing = current.current;
      if (!existing) return;

      const next = change(existing);
      current.current = next;
      setBoard(next);

      unsaved.current = next;
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => flush(), SAVE_DEBOUNCE_MS);
    },
    [flush]
  );

  // The chat returns a board the backend has already stored, so this deliberately does
  // not mark the board dirty. It also cancels any pending debounced flush: the chat
  // board is now the newest state server-side, and letting an older snapshot PUT after
  // it would clobber the assistant's change (the finding-7 race).
  const replaceBoard = useCallback(
    (next: BoardData, newRevision?: number) => {
      clearPending();
      current.current = next;
      if (newRevision !== undefined) {
        revision.current = newRevision;
      }
      setBoard(next);
    },
    [clearPending]
  );

  return {
    board,
    isSaving,
    error,
    update,
    replaceBoard,
    getRevision: () => revision.current,
  };
};
