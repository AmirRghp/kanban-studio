"use client";

import { useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { KanbanColumn } from "@/components/KanbanColumn";
import { KanbanCardPreview } from "@/components/KanbanCardPreview";
import { createId, moveCard, type BoardData } from "@/lib/kanban";

type KanbanBoardProps = {
  board: BoardData;
  onChange: (change: (current: BoardData) => BoardData) => void;
  isSaving?: boolean;
  sidebar?: ReactNode;
};

export const KanbanBoard = ({
  board,
  onChange,
  sidebar,
}: KanbanBoardProps) => {
  const [activeCardId, setActiveCardId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    // Keyboard dragging: focus a card, press Space/Enter to pick it up, arrow keys to
    // move it, Space/Enter to drop, Escape to cancel.
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveCardId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveCardId(null);

    if (!over || active.id === over.id) {
      return;
    }

    onChange((current) => ({
      ...current,
      columns: moveCard(current.columns, active.id as string, over.id as string),
    }));
  };

  const handleRenameColumn = (columnId: string, title: string) => {
    onChange((current) => ({
      ...current,
      columns: current.columns.map((column) =>
        column.id === columnId ? { ...column, title } : column
      ),
    }));
  };

  const handleAddCard = (columnId: string, title: string, details: string) => {
    const id = createId("card");
    onChange((current) => ({
      ...current,
      cards: {
        ...current.cards,
        [id]: { id, title, details: details || "No details yet." },
      },
      columns: current.columns.map((column) =>
        column.id === columnId
          ? { ...column, cardIds: [...column.cardIds, id] }
          : column
      ),
    }));
  };

  const handleDeleteCard = (columnId: string, cardId: string) => {
    onChange((current) => ({
      ...current,
      cards: Object.fromEntries(
        Object.entries(current.cards).filter(([id]) => id !== cardId)
      ),
      columns: current.columns.map((column) =>
        column.id === columnId
          ? {
              ...column,
              cardIds: column.cardIds.filter((id) => id !== cardId),
            }
          : column
      ),
    }));
  };

  const handleUpdateCard = (
    _columnId: string,
    cardId: string,
    card: { title: string; details: string; dueDate?: string | null; labels?: string[] }
  ) => {
    onChange((current) => ({
      ...current,
      cards: {
        ...current.cards,
        [cardId]: { ...current.cards[cardId], ...card },
      },
    }));
  };

  const activeCard = activeCardId ? board.cards[activeCardId] : null;
  const cardCount = Object.keys(board.cards).length;

  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute left-0 top-0 h-[420px] w-[420px] -translate-x-1/3 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,_rgba(32,157,215,0.25)_0%,_rgba(32,157,215,0.05)_55%,_transparent_70%)]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[520px] w-[520px] translate-x-1/4 translate-y-1/4 rounded-full bg-[radial-gradient(circle,_rgba(117,57,145,0.18)_0%,_rgba(117,57,145,0.05)_55%,_transparent_75%)]" />

      <main className="relative mx-auto flex max-w-[1800px] flex-col gap-6 px-6 pb-16 pt-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-xl text-sm leading-6 text-[var(--gray-text)]">
            Rename columns, drag cards between stages, and capture quick notes. Press
            Enter on a card to pick it up with the keyboard.
          </p>
          <p className="rounded-full border border-[var(--stroke)] bg-white/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]">
            {board.columns.length} columns · {cardCount} cards
          </p>
        </div>

        {/* The sidebar stacks below the board until there is room beside it. */}
        <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <section
              className="grid flex-1 gap-6 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5"
              data-testid="board-grid"
            >
              {board.columns.map((column) => (
                <KanbanColumn
                  key={column.id}
                  column={column}
                  cards={column.cardIds.map((cardId) => board.cards[cardId])}
                  onRename={handleRenameColumn}
                  onAddCard={handleAddCard}
                  onDeleteCard={handleDeleteCard}
                  onUpdateCard={handleUpdateCard}
                />
              ))}
            </section>
            <DragOverlay>
              {activeCard ? (
                <div className="w-[260px]">
                  <KanbanCardPreview card={activeCard} />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
          {sidebar}
        </div>
      </main>
    </div>
  );
};
