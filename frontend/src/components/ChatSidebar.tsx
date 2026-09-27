"use client";

import { useState, type FormEvent } from "react";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  warnings?: string[];
};

type ChatSidebarProps = {
  messages: ChatMessage[];
  isPending: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onNewChat: () => void;
};

export const ChatSidebar = ({
  messages,
  isPending,
  error,
  onSend,
  onNewChat,
}: ChatSidebarProps) => {
  const [draft, setDraft] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || isPending) return;
    onSend(text);
    setDraft("");
  };

  return (
    <aside
      className="flex w-full flex-col gap-4 rounded-3xl border border-[var(--stroke)] bg-[var(--surface-strong)] p-5 2xl:w-[360px] 2xl:shrink-0"
      data-testid="chat-sidebar"
      aria-label="AI assistant"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold text-[var(--navy-dark)]">
          Assistant
        </h2>
        <button
          type="button"
          onClick={onNewChat}
          className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[var(--gray-text)] transition hover:text-[var(--navy-dark)]"
        >
          New chat
        </button>
      </div>

      <div
        className="flex min-h-[120px] flex-1 flex-col gap-3 overflow-y-auto"
        data-testid="chat-messages"
      >
        {messages.length === 0 ? (
          <p className="text-sm leading-6 text-[var(--gray-text)]">
            No conversation yet. Ask for a change and it will be applied to the board.
            Starting a new chat clears this, but never the board.
          </p>
        ) : (
          messages.map((message) => (
            <div key={message.id} className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--gray-text)]">
                {message.role === "user" ? "You" : "Assistant"}
              </p>
              <p className="text-sm leading-6 text-[var(--navy-dark)]">
                {message.text}
              </p>
              {message.warnings && message.warnings.length > 0 && (
                <ul
                  className="space-y-1 rounded-xl border border-[var(--stroke)] bg-[var(--surface)] p-3"
                  data-testid="chat-warnings"
                >
                  {message.warnings.map((warning, index) => (
                    <li
                      key={index}
                      className="text-xs leading-5 text-[var(--gray-text)]"
                    >
                      {warning}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))
        )}
        {isPending && (
          <p className="text-sm text-[var(--gray-text)]" data-testid="chat-pending">
            Thinking...
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm font-semibold text-[var(--secondary-purple)]">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-2">
        <label className="block">
          <span className="sr-only">Message</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Add a card, move one, rename a column..."
            rows={3}
            disabled={isPending}
            aria-label="Message"
            className="w-full resize-none rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)] disabled:opacity-60"
          />
        </label>
        <button
          type="submit"
          disabled={isPending || draft.trim().length === 0}
          className="w-full rounded-full bg-[var(--secondary-purple)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white transition hover:brightness-110 disabled:opacity-60"
        >
          Send
        </button>
      </form>
    </aside>
  );
};
