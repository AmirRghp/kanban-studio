"use client";

import { useCallback, useState } from "react";
import { ChatSidebar, type ChatMessage } from "@/components/ChatSidebar";
import { KanbanBoard } from "@/components/KanbanBoard";
import { useBoard } from "@/hooks/useBoard";
import { sendChat } from "@/lib/api";

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
  const {
    board,
    isSaving,
    error: boardError,
    update,
    replaceBoard,
    getRevision,
  } = useBoard();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const handleSend = useCallback(
    async (text: string) => {
      setIsPending(true);
      setChatError(null);

      // `messages` is still the pre-update value here, which is what we want: the new
      // message travels as `message`, not duplicated into the history.
      const history = toHistory(messages);
      setMessages((previous) => [...previous, { id: nextId(), role: "user", text }]);

      try {
        const turn = await sendChat(text, history, getRevision());
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
    [messages, replaceBoard, getRevision]
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setChatError(null);
  }, []);

  if (!board) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <p data-testid="save-status" className="text-sm text-[var(--gray-text)]">
          {boardError ?? "Loading your board..."}
        </p>
      </main>
    );
  }

  return (
    <KanbanBoard
      board={board}
      isSaving={isSaving}
      error={boardError}
      onChange={update}
      onSignOut={onSignOut}
      username={username}
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
  );
};

const toHistory = (messages: ChatMessage[]) =>
  messages
    .slice(-HISTORY_LIMIT)
    .map((message) => ({ role: message.role, content: message.text }));
