"use client";

import type { ExtensionOption } from "@/lib/types";

type ChatHeroProps = {
  activeDescription?: string | null;
  activeTitle: string;
  availableExtensions: ExtensionOption[];
  onCreateThread: () => void;
  onResetThread: () => void;
  onSwitchExtension: () => void;
  selectedAlias: string;
  setSelectedAlias: (value: string) => void;
};

export function ChatHero({
  activeDescription,
  activeTitle,
  availableExtensions,
  onCreateThread,
  onResetThread,
  onSwitchExtension,
  selectedAlias,
  setSelectedAlias,
}: ChatHeroProps) {
  return (
    <header className="hero" data-testid="chat-hero">
      <div>
        <p className="eyebrow">Основной чат</p>
        <h1 data-testid="active-extension-title">{activeTitle}</h1>
        <p data-testid="active-extension-description">{activeDescription}</p>
      </div>
      <div className="hero__actions">
        <label className="field">
          <span>Extension для нового треда</span>
          <select
            data-testid="new-thread-extension-select"
            onChange={(event) => setSelectedAlias(event.target.value)}
            value={selectedAlias}
          >
            {availableExtensions.map((option) => (
              <option key={option.alias} value={option.alias}>
                {option.title}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          data-testid="new-thread-button"
          onClick={onCreateThread}
          type="button"
        >
          Новый тред
        </button>
        <button
          className="ghost-button"
          data-testid="switch-extension-button"
          onClick={onSwitchExtension}
          type="button"
        >
          Сменить extension
        </button>
        <button
          className="ghost-button"
          data-testid="reset-thread-button"
          onClick={onResetThread}
          type="button"
        >
          Сбросить
        </button>
      </div>
    </header>
  );
}
