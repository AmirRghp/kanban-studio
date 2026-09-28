import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import clsx from "clsx";
import { useState } from "react";
import { labelStyle, type Card } from "@/lib/kanban";

type CardDraft = {
  title: string;
  details: string;
  dueDate: string;
  labels: string;
};

type KanbanCardProps = {
  card: Card;
  onDelete: (cardId: string) => void;
  onUpdate?: (
    cardId: string,
    card: { title: string; details: string; dueDate: string | null; labels: string[] }
  ) => void;
};

export const KanbanCard = ({ card, onDelete, onUpdate }: KanbanCardProps) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: card.id });
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<CardDraft>(() => toDraft(card));

  const startEditing = () => {
    setDraft(toDraft(card));
    setIsEditing(true);
  };

  const submit = () => {
    const title = draft.title.trim();
    if (!title || !onUpdate) {
      setIsEditing(false);
      return;
    }
    const labels = draft.labels
      .split(",")
      .map((label) => label.trim())
      .filter(Boolean);
    onUpdate(card.id, {
      title,
      details: draft.details.trim(),
      dueDate: draft.dueDate || null,
      labels,
    });
    setIsEditing(false);
  };

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <article
      ref={setNodeRef}
      style={style}
      className={clsx(
        "rounded-2xl border border-transparent bg-white px-4 py-4 shadow-[0_12px_24px_rgba(3,33,71,0.08)]",
        "transition-all duration-150",
        isDragging && "opacity-60 shadow-[0_18px_32px_rgba(3,33,71,0.16)]"
      )}
      {...attributes}
      {...listeners}
      data-testid={`card-${card.id}`}
    >
      {isEditing ? (
        <div className="space-y-2">
          <input
            value={draft.title}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, title: event.target.value }))
            }
            onKeyDown={(event) => event.stopPropagation()}
            aria-label="Card title"
            className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm font-medium text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
            autoFocus
          />
          <textarea
            value={draft.details}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, details: event.target.value }))
            }
            onKeyDown={(event) => event.stopPropagation()}
            aria-label="Details"
            rows={3}
            className="w-full resize-none rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm text-[var(--gray-text)] outline-none transition focus:border-[var(--primary-blue)]"
          />
          <div className="flex items-center gap-2">
            <label className="flex-1 space-y-1">
              <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--gray-text)]">
                Due date
              </span>
              <input
                type="date"
                value={draft.dueDate}
                onChange={(event) =>
                  setDraft((previous) => ({ ...previous, dueDate: event.target.value }))
                }
                onKeyDown={(event) => event.stopPropagation()}
                aria-label="Due date"
                className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
              />
            </label>
          </div>
          <input
            value={draft.labels}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, labels: event.target.value }))
            }
            onKeyDown={(event) => event.stopPropagation()}
            aria-label="Labels"
            placeholder="Labels, comma separated"
            className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={submit}
              className="rounded-full bg-[var(--secondary-purple)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-blue)]"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="rounded-full border border-[var(--stroke)] px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--gray-text)] transition hover:text-[var(--navy-dark)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-blue)]"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="font-display text-base font-semibold text-[var(--navy-dark)]">
              {card.title}
            </h4>
            {card.details && (
              <p className="mt-2 text-sm leading-6 text-[var(--gray-text)]">
                {card.details}
              </p>
            )}
            {(card.dueDate || (card.labels && card.labels.length > 0)) && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {card.dueDate && <DueBadge dueDate={card.dueDate} />}
                {card.labels?.map((label) => (
                  <span
                    key={label}
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${labelStyle(label)}`}
                  >
                    {label}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            {onUpdate && (
              <button
                type="button"
                onClick={startEditing}
                className="rounded-full border border-transparent px-2 py-1 text-xs font-semibold text-[var(--gray-text)] transition hover:border-[var(--stroke)] hover:text-[var(--navy-dark)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-blue)]"
                aria-label={`Edit ${card.title}`}
              >
                Edit
              </button>
            )}
            <button
              type="button"
              onClick={() => onDelete(card.id)}
              className="rounded-full border border-transparent px-2 py-1 text-xs font-semibold text-[var(--gray-text)] transition hover:border-[var(--stroke)] hover:text-[var(--navy-dark)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-blue)]"
              aria-label={`Delete ${card.title}`}
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </article>
  );
};

const DueBadge = ({ dueDate }: { dueDate: string }) => {
  const overdue = new Date(dueDate) < new Date(new Date().toDateString());
  return (
    <span
      className={clsx(
        "rounded-full px-2 py-0.5 text-xs font-semibold",
        overdue
          ? "bg-[rgba(117,57,145,0.14)] text-[var(--secondary-purple)]"
          : "bg-[var(--surface)] text-[var(--gray-text)]"
      )}
      title={overdue ? "Past the due date" : "Due date"}
    >
      {dueDate}
    </span>
  );
};

const toDraft = (card: Card): CardDraft => ({
  title: card.title,
  details: card.details,
  dueDate: card.dueDate ?? "",
  labels: (card.labels ?? []).join(", "),
});
