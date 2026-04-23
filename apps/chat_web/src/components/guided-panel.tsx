"use client";

import { GuidedPanelShell } from "@/components/guided/guided-panel-shell";
import type { InteractionState } from "@/lib/types";

type GuidedPanelProps = {
  interaction: InteractionState | null;
  onMessage: (message: string) => Promise<void>;
  onCreateThread: (extensionAlias?: string) => Promise<void>;
};

export function GuidedPanel({
  interaction,
  onMessage,
  onCreateThread,
}: GuidedPanelProps) {
  if (!interaction) {
    return (
      <section className="guided-panel empty-state" data-testid="guided-panel-loading">
        <p className="eyebrow">Подготовка</p>
        <h1>Подключаем guided chat…</h1>
        <p>
          Как только backend вернёт первый thread, здесь появятся шаги,
          формы ввода и результаты.
        </p>
      </section>
    );
  }

  return (
    <GuidedPanelShell
      interaction={interaction}
      onCreateThread={onCreateThread}
      onMessage={onMessage}
    />
  );
}
