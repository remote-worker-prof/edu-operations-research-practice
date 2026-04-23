"use client";

import { type ReactNode, useState } from "react";

import type { InteractionState } from "@/lib/types";

type PowerConsolePanelProps = {
  commandButtons: ReactNode;
  currentStage: string | null;
  examplePayload: Record<string, unknown> | null;
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
};

export function PowerConsolePanel({
  commandButtons,
  currentStage,
  examplePayload,
  interaction,
  onMessage,
}: PowerConsolePanelProps) {
  return (
    <>
      <details
        className="card card--details"
        data-testid="power-mode-card"
        open={interaction.current_step == null || interaction.interaction_mode === "power"}
      >
        <summary>Режим преподавателя и команды</summary>
        <PowerConsole
          currentStage={currentStage}
          examplePayload={examplePayload}
          onMessage={onMessage}
        />
        <div className="command-grid command-grid--power">{commandButtons}</div>
      </details>
      <details className="card card--details" data-testid="last-intent-card">
        <summary>Последний intent</summary>
        <pre>{JSON.stringify(interaction.last_intent, null, 2)}</pre>
      </details>
      <details className="card card--details" data-testid="raw-draft-card">
        <summary>Черновик</summary>
        <pre>{JSON.stringify(interaction.draft, null, 2)}</pre>
      </details>
      <details className="card card--details" data-testid="typed-semantics-card">
        <summary>Typed semantics</summary>
        <pre>{JSON.stringify(interaction.semantics, null, 2)}</pre>
      </details>
    </>
  );
}

function PowerConsole({
  currentStage,
  examplePayload,
  onMessage,
}: {
  currentStage: string | null;
  examplePayload: Record<string, unknown> | null;
  onMessage: (message: string) => Promise<void>;
}) {
  const [message, setMessage] = useState("");

  const placeholder = currentStage
    ? `Например: /payload ${currentStage} ${JSON.stringify(examplePayload ?? {})}`
    : "Например: /help или свободный вопрос по задаче";

  return (
    <form
      className="power-console"
      data-testid="power-console"
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = message.trim();
        if (!trimmed) {
          return;
        }
        void onMessage(trimmed);
        setMessage("");
      }}
    >
      <label className="field">
        <span>Команда или сообщение</span>
        <textarea
          className="power-console__input"
          data-testid="power-console-input"
          onChange={(event) => setMessage(event.target.value)}
          placeholder={placeholder}
          rows={3}
          value={message}
        />
      </label>
      <div className="toolbar">
        <button className="ghost-button" onClick={() => setMessage("/help")} type="button">
          Вставить /help
        </button>
        <button className="primary-button" data-testid="power-console-send" type="submit">
          Отправить в чат
        </button>
      </div>
    </form>
  );
}
