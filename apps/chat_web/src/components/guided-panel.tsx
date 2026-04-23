"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  buildStageCommand,
  getSetMembers,
  initialMatrixPayload,
  initialScalarVectorPayload,
  tablePayload,
  tableRows,
  vectorLabels,
} from "@/lib/interaction";
import type {
  DisplayBlock,
  InputStepSemantics,
  InteractionState,
  MatrixShapeSemantics,
  ResultSection,
  TableShapeSemantics,
} from "@/lib/types";

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
  const [selectedAlias, setSelectedAlias] = useState<string>("study_planner");

  useEffect(() => {
    if (interaction?.active_extension) {
      setSelectedAlias(interaction.active_extension);
    }
  }, [interaction?.active_extension]);

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

  const activeExtension = interaction.available_extensions.find(
    (item) => item.alias === interaction.active_extension,
  );

  return (
    <section className="guided-panel" data-testid="guided-panel">
      <header className="hero" data-testid="chat-hero">
        <div>
          <p className="eyebrow">Основной чат</p>
          <h1 data-testid="active-extension-title">
            {activeExtension?.title ?? interaction.active_extension}
          </h1>
          <p data-testid="active-extension-description">{activeExtension?.description}</p>
        </div>
        <div className="hero__actions">
          <label className="field">
            <span>Extension для нового треда</span>
            <select
              data-testid="new-thread-extension-select"
              onChange={(event) => setSelectedAlias(event.target.value)}
              value={selectedAlias}
            >
              {interaction.available_extensions.map((option) => (
                <option key={option.alias} value={option.alias}>
                  {option.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-button"
            data-testid="new-thread-button"
            onClick={() => onCreateThread(selectedAlias)}
            type="button"
          >
            Новый тред
          </button>
          <button
            className="ghost-button"
            data-testid="switch-extension-button"
            onClick={() => void onMessage(`/use ${selectedAlias}`)}
            type="button"
          >
            Сменить extension
          </button>
          <button
            className="ghost-button"
            data-testid="reset-thread-button"
            onClick={() => void onMessage("/reset")}
            type="button"
          >
            Сбросить
          </button>
        </div>
      </header>

      <div className="status-strip" data-testid="status-strip">
        <div>
          <span className="status-strip__label">Текущий шаг</span>
          <strong data-testid="current-stage-value">
            {interaction.current_stage ?? "не выбран"}
          </strong>
        </div>
        <div>
          <span className="status-strip__label">Сводка</span>
          <strong data-testid="draft-summary-value">{interaction.draft_summary}</strong>
        </div>
        <div>
          <span className="status-strip__label">Режим</span>
          <strong data-testid="interaction-mode-value">
            {interaction.interaction_mode === "power" ? "power" : "guided"}
          </strong>
        </div>
      </div>

      <div className="quick-actions" data-testid="quick-actions">
        <button
          className="command-pill command-pill--user"
          data-testid="show-steps-button"
          onClick={() => void onMessage("/show steps")}
          type="button"
        >
          <strong>Показать этапы</strong>
          <span>Какие шаги уже готовы и что ещё осталось.</span>
        </button>
        <button
          className="command-pill command-pill--user"
          data-testid="show-draft-button"
          onClick={() => void onMessage("/show draft")}
          type="button"
        >
          <strong>Показать черновик</strong>
          <span>Проверить, какие данные уже сохранены.</span>
        </button>
        <button
          className="command-pill command-pill--user"
          data-testid="show-result-button"
          onClick={() => void onMessage("/show result")}
          type="button"
        >
          <strong>Показать результат</strong>
          <span>Вернуть краткий итог решения в чат.</span>
        </button>
        <button
          className="command-pill command-pill--user"
          data-testid="solve-button"
          onClick={() => void onMessage("/solve")}
          type="button"
        >
          <strong>Решить</strong>
          <span>Запустить расчёт после заполнения входов.</span>
        </button>
        <button
          className="command-pill command-pill--user"
          data-testid="explain-button"
          onClick={() => void onMessage("/explain")}
          type="button"
        >
          <strong>Объяснить</strong>
          <span>Попросить ассистента пояснить полученное решение.</span>
        </button>
        <button
          className="command-pill command-pill--user"
          data-testid="help-button"
          onClick={() => void onMessage("/help")}
          type="button"
        >
          <strong>Помощь</strong>
          <span>Показать быстрые подсказки по этому сценарию.</span>
        </button>
        <button
          className="command-pill command-pill--power"
          data-testid="guided-mode-button"
          onClick={() => void onMessage("/mode guided")}
          type="button"
        >
          <strong>Guided</strong>
          <span>Всегда просить подтверждение перед NL-изменениями.</span>
        </button>
        <button
          className="command-pill command-pill--power"
          data-testid="power-mode-button"
          onClick={() => void onMessage("/mode power")}
          type="button"
        >
          <strong>Power</strong>
          <span>Автоприменять хорошо grounded изменения при высокой уверенности.</span>
        </button>
      </div>

      {interaction.pending_proposals.length > 0 ? (
        <section className="card" data-testid="pending-proposals-card">
          <div className="card__header">
            <h2>Ожидают подтверждения</h2>
            <p>
              Ассистент предложил обновления для текущего черновика. Можно
              принять или отклонить их одной кнопкой.
            </p>
          </div>
          <div className="proposal-list">
            {interaction.pending_proposals.map((proposal, index) => (
              <div
                className="proposal-item"
                data-testid={`proposal-item-${index}`}
                key={`${proposal.stage_id}:${proposal.path ?? "payload"}:${index}`}
              >
                <strong>{proposal.stage_id}</strong>
                <pre>
                  {proposal.payload
                    ? JSON.stringify(proposal.payload, null, 2)
                    : `${proposal.path} = ${JSON.stringify(proposal.value)}`}
                </pre>
              </div>
            ))}
          </div>
          <div className="hero__actions">
            <button
              className="primary-button"
              data-testid="confirm-proposals-button"
              onClick={() => void onMessage("да")}
              type="button"
            >
              Применить
            </button>
            <button
              className="ghost-button"
              data-testid="reject-proposals-button"
              onClick={() => void onMessage("нет")}
              type="button"
            >
              Отклонить
            </button>
          </div>
        </section>
      ) : null}

      <div className="workspace-grid">
        <section className="card">
          <div className="card__header">
            <h2>Этапы</h2>
            <p>{interaction.pending_question}</p>
          </div>
          <div className="stage-list">
            {interaction.stage_statuses.map((stage) => (
              <button
                className={`stage-tile${stage.current ? " stage-tile--current" : ""}${
                  stage.ready ? " stage-tile--ready" : ""
                }`}
                data-testid={`stage-tile-${stage.stage_id}`}
                key={stage.stage_id}
                onClick={() => void onMessage(`/step ${stage.stage_id}`)}
                type="button"
              >
                <div className="stage-tile__head">
                  <strong>{stage.label}</strong>
                  <span>{stage.ready ? "готово" : "ожидает"}</span>
                </div>
                <p>{stage.expectation_hint}</p>
                {stage.errors.map((error) => (
                  <small key={error}>{error}</small>
                ))}
              </button>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="card__header">
            <h2>Ввод данных</h2>
            <p>
              Рабочая форма строится автоматически из typed semantics текущего
              extension.
            </p>
          </div>
          <StepEditor interaction={interaction} onMessage={onMessage} />
        </section>

        <section className="card">
          <div className="card__header">
            <h2>Результаты</h2>
            <p>
              Здесь показываются те же result blocks, которые backend уже
              строит для deterministic runtime.
            </p>
          </div>
          <ResultView sections={interaction.result_sections} />
        </section>
      </div>

      <div className="details-grid">
        <details
          className="card card--details"
          data-testid="power-mode-card"
          open={interaction.current_step == null || interaction.interaction_mode === "power"}
        >
          <summary>Режим преподавателя и команды</summary>
          <PowerConsole
            currentStage={interaction.current_stage ?? null}
            examplePayload={interaction.expected_payload ?? null}
            onMessage={onMessage}
          />
          <div className="command-grid command-grid--power">
            {interaction.commands.map((command) => (
              <button
                className={`command-pill command-pill--${command.category}`}
                key={command.name}
                onClick={() => {
                  if (command.name === "/show") {
                    void onMessage("/show steps");
                    return;
                  }
                  if (command.name === "/new") {
                    void onMessage(`/new ${interaction.active_extension}`);
                    return;
                  }
                  if (command.name === "/use") {
                    void onMessage(`/use ${selectedAlias}`);
                    return;
                  }
                  if (command.name === "/step" && interaction.current_stage) {
                    void onMessage(`/step ${interaction.current_stage}`);
                    return;
                  }
                  if (command.name === "/payload" && interaction.current_stage) {
                    const payload = interaction.expected_payload ?? {};
                    void onMessage(buildStageCommand(interaction.current_stage, payload));
                    return;
                  }
                  if (command.name === "/mode") {
                    void onMessage(
                      interaction.interaction_mode === "guided"
                        ? "/mode power"
                        : "/mode guided",
                    );
                    return;
                  }
                  void onMessage(command.name);
                }}
                type="button"
              >
                <strong>{command.name}</strong>
                <span>{command.summary}</span>
              </button>
            ))}
          </div>
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
      </div>
    </section>
  );
}

function StepEditor({
  interaction,
  onMessage,
}: {
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
}) {
  const step = interaction.current_step;

  if (!step) {
    return (
      <div className="empty-state compact" data-testid="plain-chat-hint">
        <p>
          Для этого сценария основной режим работы сейчас идёт через обычный чат.
          Ниже в блоке преподавателя можно отправить команду или свободный вопрос.
        </p>
      </div>
    );
  }

  if (step.shape?.kind === "table") {
    return (
      <TableEditor
        interaction={interaction}
        onMessage={onMessage}
        shape={step.shape}
        step={step}
      />
    );
  }

  if (step.shape?.kind === "matrix") {
    return (
      <MatrixEditor
        interaction={interaction}
        onMessage={onMessage}
        shape={step.shape}
        step={step}
      />
    );
  }

  return <ScalarVectorEditor interaction={interaction} onMessage={onMessage} step={step} />;
}

function ScalarVectorEditor({
  interaction,
  step,
  onMessage,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  onMessage: (message: string) => Promise<void>;
}) {
  const [payload, setPayload] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setPayload(initialScalarVectorPayload(interaction, step));
  }, [interaction, step]);

  return (
    <form
      className="editor-form"
      data-testid={`editor-${step.step_id}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onMessage(buildStageCommand(step.step_id, payload));
      }}
    >
      {step.scalars.map((field) => (
        <label className="field" key={field.field_path}>
          <span>{field.label}</span>
          <input
            data-testid={`scalar-${step.step_id}-${field.field_path}`}
            onChange={(event) =>
              setPayload((current) => ({
                ...current,
                [field.field_path]:
                  field.value_type === "number"
                    ? Number(event.target.value)
                    : event.target.value,
              }))
            }
            type={field.value_type === "number" ? "number" : "text"}
            value={String(payload[field.field_path] ?? "")}
          />
          <small>{field.help}</small>
        </label>
      ))}

      {step.vectors.map((field) => {
        const labels = vectorLabels(interaction, field);
        const values = Array.isArray(payload[field.field_path])
          ? (payload[field.field_path] as unknown[])
          : [];
        return (
          <div className="vector-editor" key={field.field_path}>
            <h3>{field.label}</h3>
            <p>{field.help}</p>
            <div className="vector-editor__rows">
              {labels.map((label, index) => (
                <label className="field field--inline" key={`${field.field_path}:${label}`}>
                  <span>{label}</span>
                  <input
                    data-testid={`vector-${step.step_id}-${field.field_path}-${index}`}
                    onChange={(event) =>
                      setPayload((current) => {
                        const next = [...(Array.isArray(current[field.field_path]) ? (current[field.field_path] as unknown[]) : values)];
                        next[index] = Number(event.target.value);
                        return {
                          ...current,
                          [field.field_path]: next,
                        };
                      })
                    }
                    type="number"
                    value={String(values[index] ?? "")}
                  />
                </label>
              ))}
            </div>
          </div>
        );
      })}

      <button
        className="primary-button"
        data-testid={`submit-step-${step.step_id}`}
        type="submit"
      >
        Отправить шаг
      </button>
    </form>
  );
}

function TableEditor({
  interaction,
  step,
  shape,
  onMessage,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  shape: TableShapeSemantics;
  onMessage: (message: string) => Promise<void>;
}) {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    setRows(tableRows(interaction, step.step_id, shape));
  }, [interaction, shape, step.step_id]);

  return (
    <form
      className="editor-form"
      data-testid={`table-editor-${step.step_id}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onMessage(buildStageCommand(step.step_id, tablePayload(rows, shape)));
      }}
    >
      <div className="table-editor">
        <div className="table-editor__grid table-editor__grid--header">
          <strong>{shape.key.label}</strong>
          {shape.columns.map((column) => (
            <strong key={column.field_path}>{column.label}</strong>
          ))}
        </div>
        {rows.map((row, rowIndex) => (
          <div className="table-editor__grid" key={`row-${rowIndex}`}>
            <input
              data-testid={`table-${step.step_id}-${rowIndex}-${shape.key.field_path}`}
              onChange={(event) =>
                setRows((current) =>
                  current.map((item, index) =>
                    index === rowIndex
                      ? { ...item, [shape.key.field_path]: event.target.value }
                      : item,
                  ),
                )
              }
              type="text"
              value={String(row[shape.key.field_path] ?? "")}
            />
            {shape.columns.map((column) => (
              <input
                data-testid={`table-${step.step_id}-${rowIndex}-${column.field_path}`}
                key={`${rowIndex}:${column.field_path}`}
                onChange={(event) =>
                  setRows((current) =>
                    current.map((item, index) =>
                      index === rowIndex
                        ? {
                            ...item,
                            [column.field_path]:
                              column.value_type === "number"
                                ? Number(event.target.value)
                                : event.target.value,
                          }
                        : item,
                    ),
                  )
                }
                type={column.value_type === "number" ? "number" : "text"}
                value={String(row[column.field_path] ?? "")}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="toolbar">
        <button
          className="ghost-button"
          data-testid={`add-row-${step.step_id}`}
          onClick={() =>
            setRows((current) => [
              ...current,
              {
                [shape.key.field_path]: "",
                ...Object.fromEntries(shape.columns.map((column) => [column.field_path, 0])),
              },
            ])
          }
          type="button"
        >
          Добавить строку
        </button>
        <button
          className="primary-button"
          data-testid={`submit-step-${step.step_id}`}
          type="submit"
        >
          Отправить таблицу
        </button>
      </div>
    </form>
  );
}

function MatrixEditor({
  interaction,
  step,
  shape,
  onMessage,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  shape: MatrixShapeSemantics;
  onMessage: (message: string) => Promise<void>;
}) {
  const [payload, setPayload] = useState<Record<string, number[][]>>({});

  const rowLabels = useMemo(
    () => getSetMembers(interaction, shape.row_set),
    [interaction, shape.row_set],
  );
  const colLabels = useMemo(
    () => getSetMembers(interaction, shape.col_set),
    [interaction, shape.col_set],
  );

  useEffect(() => {
    setPayload(initialMatrixPayload(interaction, step.step_id, shape));
  }, [interaction, shape, step.step_id]);

  if (rowLabels.length === 0 || colLabels.length === 0) {
    return (
      <div className="empty-state compact">
        <p>
          Сначала заполните множества `{shape.row_set}` и `{shape.col_set}`,
          чтобы редактор матрицы знал порядок строк и столбцов.
        </p>
      </div>
    );
  }

  return (
    <form
      className="editor-form"
      data-testid={`matrix-editor-${step.step_id}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onMessage(buildStageCommand(step.step_id, payload));
      }}
    >
      {shape.fields.map((field) => (
        <div className="matrix-editor" key={field.field_path}>
          <h3>{field.label}</h3>
          <div
            className="matrix-editor__grid"
            style={{
              gridTemplateColumns: `minmax(120px, 1.1fr) repeat(${colLabels.length}, minmax(72px, 1fr))`,
            }}
          >
            <span />
            {colLabels.map((label) => (
              <strong key={label}>{label}</strong>
            ))}
            {rowLabels.map((rowLabel, rowIndex) => (
              <FragmentRow key={rowLabel} label={rowLabel}>
                {colLabels.map((colLabel, colIndex) => (
                  <input
                    data-testid={`matrix-${step.step_id}-${field.field_path}-${rowIndex}-${colIndex}`}
                    key={`${rowLabel}:${colLabel}`}
                    onChange={(event) =>
                      setPayload((current) => {
                        const matrix = current[field.field_path].map((row) => [...row]);
                        matrix[rowIndex][colIndex] = Number(event.target.value);
                        return {
                          ...current,
                          [field.field_path]: matrix,
                        };
                      })
                    }
                    type="number"
                    value={String(payload[field.field_path]?.[rowIndex]?.[colIndex] ?? "")}
                  />
                ))}
              </FragmentRow>
            ))}
          </div>
        </div>
      ))}
      <button
        className="primary-button"
        data-testid={`submit-step-${step.step_id}`}
        type="submit"
      >
        Отправить матрицу
      </button>
    </form>
  );
}

function FragmentRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <>
      <strong>{label}</strong>
      {children}
    </>
  );
}

function ResultView({ sections }: { sections: ResultSection[] }) {
  if (sections.length === 0) {
    return (
      <div className="empty-state compact" data-testid="empty-result-state">
        <p>Результат появится здесь после кнопки «Решить» или команды /solve.</p>
      </div>
    );
  }

  return (
    <div className="results-stack" data-testid="results-stack">
      {sections.map((section) => (
        <article className="result-section" key={section.section_id}>
          <h3 data-testid="result-section-title">{section.title}</h3>
          {section.blocks.map((block, index) => (
            <ResultBlockView block={block} key={`${section.section_id}:${index}`} />
          ))}
        </article>
      ))}
    </div>
  );
}

function ResultBlockView({ block }: { block: DisplayBlock }) {
  if (block.type === "summary") {
    return (
      <p className="summary-block" data-testid="result-summary-block">
        {block.text}
      </p>
    );
  }

  if (block.type === "kv") {
    return (
      <div className="summary-grid">
        {block.items.map((item) => (
          <div className="summary-card" data-testid="result-kv-card" key={item.key}>
            <span>{item.key}</span>
            <strong>{String(item.value)}</strong>
          </div>
        ))}
      </div>
    );
  }

  if (block.type === "table") {
    return (
      <div className="result-table">
        <div className="result-table__row result-table__row--header">
          {block.columns.map((column) => (
            <strong key={column}>{column}</strong>
          ))}
        </div>
        {block.rows.map((row, rowIndex) => (
          <div className="result-table__row" data-testid="result-table-row" key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <span key={`${rowIndex}:${cellIndex}`}>{String(cell)}</span>
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (block.type === "list") {
    return (
      <ul className="result-list">
        {block.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
  }

  return <pre>{JSON.stringify(block.value, null, 2)}</pre>;
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
    ? `Например: ${buildStageCommand(currentStage, examplePayload ?? {})}`
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
