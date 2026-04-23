"use client";

import type { ThreadSummary } from "@/lib/types";

type ThreadListProps = {
  threads: ThreadSummary[];
  activeThreadId?: string;
  onSelect: (threadId: string) => void;
  onDelete: (threadId: string) => void;
  onCreate: () => void;
};

export function ThreadList({
  threads,
  activeThreadId,
  onSelect,
  onDelete,
  onCreate,
}: ThreadListProps) {
  return (
    <aside className="thread-list" data-testid="thread-list">
      <div className="thread-list__header">
        <div>
          <p className="eyebrow">Треды</p>
          <h2>Сценарии</h2>
        </div>
        <button
          className="primary-button"
          data-testid="thread-list-create-button"
          onClick={onCreate}
          type="button"
        >
          Новый
        </button>
      </div>
      <div className="thread-list__items">
        {threads.map((thread) => {
          const active = thread.thread_id === activeThreadId;
          return (
            <article
              className={`thread-card${active ? " thread-card--active" : ""}`}
              data-testid={`thread-card-${thread.thread_id}`}
              key={thread.thread_id}
            >
              <div className="thread-card__meta">
                <span>{thread.extension_title}</span>
                <span>{new Date(thread.updated_at).toLocaleTimeString("ru-RU")}</span>
              </div>
              <button
                className="thread-card__open"
                data-testid={`thread-open-${thread.thread_id}`}
                onClick={() => onSelect(thread.thread_id)}
                type="button"
              >
                <strong>{thread.last_user_message ?? "Новый сценарий"}</strong>
              </button>
              <p>{thread.pending_question ?? "Готов к вводу данных."}</p>
              <span className="thread-card__count">
                сообщений: {thread.message_count}
              </span>
              <button
                className="thread-card__delete"
                data-testid={`thread-delete-${thread.thread_id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(thread.thread_id);
                }}
                type="button"
              >
                удалить
              </button>
            </article>
          );
        })}
      </div>
    </aside>
  );
}
