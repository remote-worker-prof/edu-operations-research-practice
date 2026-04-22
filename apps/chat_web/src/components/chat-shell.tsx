"use client";

import { useEffect, useRef, useState } from "react";

import { useCopilotChat } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { MessageRole, TextMessage } from "@copilotkit/runtime-client-gql";

import { GuidedPanel } from "@/components/guided-panel";
import { ThreadList } from "@/components/thread-list";
import {
  backendRuntimeUrl,
  createThread,
  deleteThread,
  getThread,
  listThreads,
} from "@/lib/api";
import type { InteractionState, ThreadSummary } from "@/lib/types";

type ChatShellProps = {
  threadId?: string;
  onThreadIdChange: (threadId: string) => void;
};

export function ChatShell({ threadId, onThreadIdChange }: ChatShellProps) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [interaction, setInteraction] = useState<InteractionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prevLoading = useRef(false);

  const { appendMessage, isLoading } = useCopilotChat();

  async function refreshThreads(selectedThreadId?: string) {
    const nextThreads = await listThreads();
    setThreads(nextThreads);
    const activeId = selectedThreadId ?? threadId;
    if (activeId) {
      const envelope = await getThread(activeId);
      setInteraction(envelope.interaction);
    }
  }

  async function ensureInitialThread() {
    if (threadId) {
      await refreshThreads(threadId);
      return;
    }
    const envelope = await createThread("study_planner");
    onThreadIdChange(envelope.thread.thread_id);
    setInteraction(envelope.interaction);
    setThreads(await listThreads());
  }

  useEffect(() => {
    void ensureInitialThread().catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Не удалось подключить backend.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!threadId) {
      return;
    }
    void refreshThreads(threadId).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить thread.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  useEffect(() => {
    if (prevLoading.current && !isLoading && threadId) {
      void refreshThreads(threadId).catch((caught) => {
        setError(
          caught instanceof Error ? caught.message : "Не удалось синхронизировать состояние.",
        );
      });
    }
    prevLoading.current = isLoading;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, threadId]);

  async function sendCommand(command: string) {
    setError(null);
    await appendMessage(
      new TextMessage({
        role: MessageRole.User,
        content: command,
      }),
    );
  }

  async function createNewThread(extensionAlias?: string) {
    setError(null);
    const envelope = await createThread(extensionAlias);
    onThreadIdChange(envelope.thread.thread_id);
    setInteraction(envelope.interaction);
    setThreads(await listThreads());
  }

  async function removeThread(targetThreadId: string) {
    setError(null);
    await deleteThread(targetThreadId);
    const nextThreads = await listThreads();
    setThreads(nextThreads);
    if (threadId === targetThreadId) {
      if (nextThreads[0]) {
        onThreadIdChange(nextThreads[0].thread_id);
        const envelope = await getThread(nextThreads[0].thread_id);
        setInteraction(envelope.interaction);
      } else {
        const envelope = await createThread("study_planner");
        onThreadIdChange(envelope.thread.thread_id);
        setInteraction(envelope.interaction);
        setThreads(await listThreads());
      }
    }
  }

  return (
    <CopilotSidebar
      className="chat-shell__sidebar"
      clickOutsideToClose={false}
      defaultOpen
      disableSystemMessage
      labels={{
        title: "Учебный AI-чат",
        initial:
          "Я веду вас по шагам, а не заставляю помнить команды. Слева выбирайте сценарий, в центре заполняйте формы, справа чат.",
      }}
      suggestions={[
        { title: "Подсказка", message: "/help" },
        { title: "Показать этапы", message: "/show steps" },
        { title: "Показать черновик", message: "/show draft" },
      ]}
    >
      <main className="chat-shell">
        <ThreadList
          activeThreadId={threadId}
          onCreate={() => {
            void createNewThread(interaction?.active_extension);
          }}
          onDelete={(targetThreadId) => {
            void removeThread(targetThreadId);
          }}
          onSelect={onThreadIdChange}
          threads={threads}
        />
        <div className="chat-shell__main">
          <div className="runtime-banner">
            <span>CopilotKit runtime</span>
            <code>{backendRuntimeUrl()}</code>
          </div>
          {error ? <div className="error-banner">{error}</div> : null}
          <GuidedPanel
            interaction={interaction}
            onCommand={async (command) => {
              try {
                await sendCommand(command);
              } catch (caught) {
                setError(
                  caught instanceof Error
                    ? caught.message
                    : "Не удалось отправить команду в чат.",
                );
              }
            }}
            onCreateThread={createNewThread}
          />
        </div>
      </main>
    </CopilotSidebar>
  );
}
