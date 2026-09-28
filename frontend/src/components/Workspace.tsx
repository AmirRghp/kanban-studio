"use client";

import { useCallback, useEffect, useState } from "react";
import { ChatSidebar, type ChatMessage } from "@/components/ChatSidebar";
import { KanbanBoard } from "@/components/KanbanBoard";
import { TopBar } from "@/components/TopBar";
import { useBoard } from "@/hooks/useBoard";
import {
  createBoard,
  deleteBoard,
  listBoards,
  renameBoard,
  sendChat,
  type BoardSummary,
} from "@/lib/api";

// Matches HISTORY_LIMIT in the backend. The browser trims too, so the request stays
// small without depending on the server to do it.
const HISTORY_LIMIT = 20;

type WorkspaceProps = {
  username: string;
  onSignOut: () => void;
};

let messageCounter = 0;
const nextId = () => {
  messageCounter += 1;
  return `m${messageCounter}`;
};

export const Workspace = ({ username, onSignOut }: WorkspaceProps) => {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [boardsError, setBoardsError] = useState<string | null>(null);
  const [activeBoardId, setActiveBoardId] = useState<number | null>(null);

  const {
    board,
    isSaving,
    error: boardError,
    update,
    replaceBoard,
    getRevision,
  } = useBoard(activeBoardId);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listBoards()
      .then((list) => {
        if (cancelled) return;
        setBoards(list);
        // Land on the first board; a returning user's first board is their oldest.
        if (list.length > 0) setActiveBoardId(list[0].id);
      })
      .catch(() => {
        if (!cancelled) setBoardsError("Could not load your boards.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      if (activeBoardId === null) return;
      setIsPending(true);
      setChatError(null);

      // `messages` is still the pre-update value here, which is what we want: the new
      // message travels as `message`, not duplicated into the history.
      const history = toHistory(messages);
      setMessages((previous) => [...previous, { id: nextId(), role: "user", text }]);

      try {
        const turn = await sendChat(activeBoardId, text, history, getRevision());
        replaceBoard(turn.board, turn.revision);
        setMessages((previous) => [
          ...previous,
          {
            id: nextId(),
            role: "assistant",
            text: turn.reply,
            warnings: turn.warnings,
          },
        ]);
      } catch {
        setChatError("The assistant could not be reached. Try again.");
      } finally {
        setIsPending(false);
      }
    },
    [activeBoardId, messages, replaceBoard, getRevision]
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setChatError(null);
  }, []);

  const handleCreateBoard = useCallback(async (name: string) => {
    try {
      const created = await createBoard(name);
      setBoards((previous) => [...previous, created]);
      setActiveBoardId(created.id);
      setBoardsError(null);
    } catch {
      setBoardsError("Could not create that board.");
    }
  }, []);

  const handleRenameBoard = useCallback(async (boardId: number, name: string) => {
    try {
      await renameBoard(boardId, name);
      setBoards((previous) =>
        previous.map((entry) =>
          entry.id === boardId ? { ...entry, name } : entry
        )
      );
      setBoardsError(null);
    } catch {
      setBoardsError("Could not rename that board.");
    }
  }, []);

  const handleDeleteBoard = useCallback(
    async (boardId: number) => {
      try {
        await deleteBoard(boardId);
        setBoards((previous) => previous.filter((entry) => entry.id !== boardId));
        if (activeBoardId === boardId) {
          setActiveBoardId(null);
        }
        setBoardsError(null);
      } catch {
        setBoardsError("Could not delete that board.");
      }
    },
    [activeBoardId]
  );

  // A new board loads to null; show the chooser state rather than a fake board.
  if (boardsError && boards.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <p data-testid="save-status" className="text-sm text-[var(--gray-text)]">
          {boardsError}
        </p>
      </main>
    );
  }

  const saveStatus = boardError ?? (isSaving ? "Saving" : "All changes saved");

  return (
    <div className="min-h-screen">
      <TopBar
        username={username}
        boards={boards}
        activeBoardId={activeBoardId}
        onSelectBoard={setActiveBoardId}
        onCreateBoard={handleCreateBoard}
        onRenameBoard={handleRenameBoard}
        onDeleteBoard={handleDeleteBoard}
        saveStatus={saveStatus}
        isStatusError={boardError !== null}
        onSignOut={onSignOut}
      />
      {!board ? (
        <main className="flex min-h-[60vh] items-center justify-center px-6">
          <p data-testid="board-loading" className="text-sm text-[var(--gray-text)]">
            {boardError ??
              (activeBoardId === null
                ? "Select a board from the switcher above, or create one."
                : "Loading your board...")}
          </p>
        </main>
      ) : (
        <KanbanBoard
          board={board}
          isSaving={isSaving}
          onChange={update}
          sidebar={
            <ChatSidebar
              messages={messages}
              isPending={isPending}
              error={chatError}
              onSend={handleSend}
              onNewChat={handleNewChat}
            />
          }
        />
      )}
    </div>
  );
};

const toHistory = (messages: ChatMessage[]) =>
  messages
    .slice(-HISTORY_LIMIT)
    .map((message) => ({ role: message.role, content: message.text }));
