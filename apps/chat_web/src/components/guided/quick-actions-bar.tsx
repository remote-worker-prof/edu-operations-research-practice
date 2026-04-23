"use client";

type QuickActionsBarProps = {
  onExplain: () => void;
  onGuidedMode: () => void;
  onHelp: () => void;
  onPowerMode: () => void;
  onShowDraft: () => void;
  onShowResult: () => void;
  onShowSteps: () => void;
  onSolve: () => void;
};

export function QuickActionsBar({
  onExplain,
  onGuidedMode,
  onHelp,
  onPowerMode,
  onShowDraft,
  onShowResult,
  onShowSteps,
  onSolve,
}: QuickActionsBarProps) {
  return (
    <div className="quick-actions" data-testid="quick-actions">
      <button
        className="command-pill command-pill--user"
        data-testid="show-steps-button"
        onClick={onShowSteps}
        type="button"
      >
        <strong>Показать этапы</strong>
        <span>Какие шаги уже готовы и что ещё осталось.</span>
      </button>
      <button
        className="command-pill command-pill--user"
        data-testid="show-draft-button"
        onClick={onShowDraft}
        type="button"
      >
        <strong>Показать черновик</strong>
        <span>Проверить, какие данные уже сохранены.</span>
      </button>
      <button
        className="command-pill command-pill--user"
        data-testid="show-result-button"
        onClick={onShowResult}
        type="button"
      >
        <strong>Показать результат</strong>
        <span>Вернуть краткий итог решения в чат.</span>
      </button>
      <button
        className="command-pill command-pill--user"
        data-testid="solve-button"
        onClick={onSolve}
        type="button"
      >
        <strong>Решить</strong>
        <span>Запустить расчёт после заполнения входов.</span>
      </button>
      <button
        className="command-pill command-pill--user"
        data-testid="explain-button"
        onClick={onExplain}
        type="button"
      >
        <strong>Объяснить</strong>
        <span>Попросить ассистента пояснить полученное решение.</span>
      </button>
      <button
        className="command-pill command-pill--user"
        data-testid="help-button"
        onClick={onHelp}
        type="button"
      >
        <strong>Помощь</strong>
        <span>Показать быстрые подсказки по этому сценарию.</span>
      </button>
      <button
        className="command-pill command-pill--power"
        data-testid="guided-mode-button"
        onClick={onGuidedMode}
        type="button"
      >
        <strong>Guided</strong>
        <span>Всегда просить подтверждение перед NL-изменениями.</span>
      </button>
      <button
        className="command-pill command-pill--power"
        data-testid="power-mode-button"
        onClick={onPowerMode}
        type="button"
      >
        <strong>Power</strong>
        <span>Автоприменять хорошо grounded изменения при высокой уверенности.</span>
      </button>
    </div>
  );
}
