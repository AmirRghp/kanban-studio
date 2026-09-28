import { labelStyle, type Card } from "@/lib/kanban";

type KanbanCardPreviewProps = {
  card: Card;
};

export const KanbanCardPreview = ({ card }: KanbanCardPreviewProps) => (
  <article className="rotate-2 rounded-2xl border border-transparent bg-white px-4 py-4 shadow-[0_18px_32px_rgba(3,33,71,0.16)]">
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
            {card.dueDate && (
              <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-xs font-semibold text-[var(--gray-text)]">
                {card.dueDate}
              </span>
            )}
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
    </div>
  </article>
);
