"use client";

import { useEffect, useRef, useState } from "react";
import type { BoardSummary } from "@/lib/api";

type TopBarProps = {
  username: string;
  boards: BoardSummary[];
  activeBoardId: number | null;
  onSelectBoard: (boardId: number) => void;
  onCreateBoard: (name: string) => void;
  onRenameBoard: (boardId: number, name: string) => void;
  onDeleteBoard: (boardId: number) => void;
  saveStatus: string;
  isStatusError: boolean;
  onSignOut: () => void;
};

export const TopBar = ({
  username,
  boards,
  activeBoardId,
  onSelectBoard,
  onCreateBoard,
  onRenameBoard,
  onDeleteBoard,
  saveStatus,
  isStatusError,
  onSignOut,
}: TopBarProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const active = boards.find((board) => board.id === activeBoardId) ?? null;

  useEffect(() => {
    if (!isOpen) return;
    const onClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        event.target instanceof Node &&
        !containerRef.current.contains(event.target)
      ) {
        setIsOpen(false);
        setIsCreating(false);
        setRenamingId(null);
        setConfirmingDeleteId(null);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [isOpen]);

  const closeMenus = () => {
    setIsCreating(false);
    setRenamingId(null);
    setConfirmingDeleteId(null);
    setNewName("");
  };

  const handleCreate = () => {
    const name = newName.trim();
    if (!name) return;
    onCreateBoard(name);
    setNewName("");
    setIsCreating(false);
    setIsOpen(false);
  };

  const handleRename = () => {
    const name = renameValue.trim();
    if (!name || renamingId === null) return;
    onRenameBoard(renamingId, name);
    setRenamingId(null);
  };

  const handleDelete = (boardId: number) => {
    onDeleteBoard(boardId);
    setConfirmingDeleteId(null);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--stroke)] bg-white/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1800px] items-center gap-4 px-6">
        <h1 className="font-display text-lg font-semibold text-[var(--navy-dark)]">
          Kanban Studio
        </h1>

        <div className="relative" ref={containerRef}>
          <button
            type="button"
            onClick={() => setIsOpen((open) => !open)}
            aria-expanded={isOpen}
            aria-haspopup="listbox"
            data-testid="board-switcher"
            className="flex items-center gap-2 rounded-full border border-[var(--stroke)] px-4 py-2 text-sm font-semibold text-[var(--navy-dark)] transition hover:border-[var(--primary-blue)]"
          >
            <span className="h-2 w-2 rounded-full bg-[var(--accent-yellow)]" />
            <span className="max-w-[220px] truncate">
              {active ? active.name : "Choose a board"}
            </span>
            <span aria-hidden className="text-[var(--gray-text)]">
              ▾
            </span>
          </button>

          {isOpen && (
            <div
              role="listbox"
              aria-label="Your boards"
              data-testid="board-menu"
              className="absolute left-0 top-12 w-72 rounded-2xl border border-[var(--stroke)] bg-[var(--surface-strong)] p-2 shadow-[var(--shadow)]"
            >
              {boards.length === 0 && (
                <p className="px-3 py-3 text-sm text-[var(--gray-text)]">
                  No boards yet. Create your first one below.
                </p>
              )}
              {boards.map((board) => (
                <div key={board.id} className="rounded-xl px-1">
                  {renamingId === board.id ? (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        handleRename();
                      }}
                      className="flex items-center gap-2 p-2"
                    >
                      <input
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        autoFocus
                        aria-label="Board name"
                        className="w-full rounded-lg border border-[var(--stroke)] px-2 py-1 text-sm outline-none focus:border-[var(--primary-blue)]"
                      />
                      <button
                        type="submit"
                        className="rounded-full bg-[var(--secondary-purple)] px-3 py-1 text-xs font-semibold text-white"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenamingId(null)}
                        className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs font-semibold text-[var(--gray-text)]"
                      >
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        role="option"
                        aria-selected={board.id === activeBoardId}
                        onClick={() => {
                          onSelectBoard(board.id);
                          setIsOpen(false);
                          closeMenus();
                        }}
                        className={`flex-1 truncate rounded-lg px-3 py-2 text-left text-sm transition hover:bg-[var(--surface)] ${
                          board.id === activeBoardId
                            ? "font-semibold text-[var(--navy-dark)]"
                            : "text-[var(--gray-text)]"
                        }`}
                      >
                        {board.name}
                        <span className="ml-2 text-xs text-[var(--gray-text)]">
                          {board.cardCount} cards
                        </span>
                      </button>
                      <button
                        type="button"
                        aria-label={`Rename ${board.name}`}
                        onClick={() => {
                          setRenameValue(board.name);
                          setRenamingId(board.id);
                        }}
                        className="rounded-full px-2 py-1 text-xs font-semibold text-[var(--gray-text)] transition hover:text-[var(--navy-dark)]"
                      >
                        Rename
                      </button>
                      {confirmingDeleteId === board.id ? (
                        <button
                          type="button"
                          onClick={() => handleDelete(board.id)}
                          data-testid={`confirm-delete-${board.id}`}
                          className="rounded-full bg-[var(--secondary-purple)] px-2 py-1 text-xs font-semibold text-white"
                        >
                          Delete?
                        </button>
                      ) : (
                        <button
                          type="button"
                          aria-label={`Delete ${board.name}`}
                          onClick={() => setConfirmingDeleteId(board.id)}
                          className="rounded-full px-2 py-1 text-xs font-semibold text-[var(--gray-text)] transition hover:text-[var(--secondary-purple)]"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {isCreating ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleCreate();
                  }}
                  className="flex items-center gap-2 p-2"
                >
                  <input
                    value={newName}
                    onChange={(event) => setNewName(event.target.value)}
                    placeholder="Board name"
                    aria-label="New board name"
                    autoFocus
                    className="w-full rounded-lg border border-[var(--stroke)] px-2 py-1 text-sm outline-none focus:border-[var(--primary-blue)]"
                  />
                  <button
                    type="submit"
                    className="rounded-full bg-[var(--secondary-purple)] px-3 py-1 text-xs font-semibold text-white"
                  >
                    Create
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsCreating(false)}
                    className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs font-semibold text-[var(--gray-text)]"
                  >
                    Cancel
                  </button>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setIsCreating(true)}
                  className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-[var(--primary-blue)] transition hover:bg-[var(--surface)]"
                >
                  + New board
                </button>
              )}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-4">
          <p
            data-testid="save-status"
            aria-live="polite"
            className={`text-xs font-semibold uppercase tracking-[0.2em] ${
              isStatusError ? "text-[var(--secondary-purple)]" : "text-[var(--gray-text)]"
            }`}
          >
            {saveStatus}
          </p>
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--gray-text)] transition hover:text-[var(--navy-dark)]"
          >
            Sign out{username ? ` (${username})` : ""}
          </button>
        </div>
      </div>
    </header>
  );
};
