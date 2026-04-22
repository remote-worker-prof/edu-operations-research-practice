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
  onCommand: (command: string) => Promise<void>;
  onCreateThread: (extensionAlias?: string) => Promise<void>;
};

export function GuidedPanel({
  interaction,
  onCommand,
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
      <section className="guided-panel empty-state">
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
    <section className="guided-panel">
      <header className="hero">
        <div>
          <p className="eyebrow">Semantics-driven workspace</p>
          <h1>{activeExtension?.title ?? interaction.active_extension}</h1>
          <p>{activeExtension?.description}</p>
        </div>
        <div className="hero__actions">
          <label className="field">
            <span>Шаблон нового треда</span>
            <select
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
            onClick={() => onCreateThread(selectedAlias)}
            type="button"
          >
            Новый тред
          </button>
          <button
            className="ghost-button"
            onClick={() => onCommand(`/new ${interaction.active_extension}`)}
            type="button"
          >
            Очистить текущий
          </button>
        </div>
      </header>

      <div className="status-strip">
        <div>
          <span className="status-strip__label">Текущий шаг</span>
          <strong>{interaction.current_stage ?? "не выбран"}</strong>
        </div>
        <div>
          <span className="status-strip__label">Сводка</span>
          <strong>{interaction.draft_summary}</strong>
        </div>
      </div>

      <div className="command-grid">
        {interaction.commands.map((command) => (
          <button
            className={`command-pill command-pill--${command.category}`}
            key={command.name}
            onClick={() => {
              if (command.name === "/show") {
                void onCommand("/show steps");
                return;
              }
              if (command.name === "/new") {
                void onCommand(`/new ${interaction.active_extension}`);
                return;
              }
              if (command.name === "/use") {
                void onCommand(`/use ${selectedAlias}`);
                return;
              }
              if (command.name === "/step" && interaction.current_stage) {
                void onCommand(`/step ${interaction.current_stage}`);
                return;
              }
              if (command.name === "/payload" && interaction.current_stage) {
                const payload = interaction.expected_payload ?? {};
                void onCommand(buildStageCommand(interaction.current_stage, payload));
                return;
              }
              void onCommand(command.name);
            }}
            type="button"
          >
            <strong>{command.name}</strong>
            <span>{command.summary}</span>
          </button>
        ))}
      </div>

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
                key={stage.stage_id}
                onClick={() => onCommand(`/step ${stage.stage_id}`)}
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
          <StepEditor interaction={interaction} onCommand={onCommand} />
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
        <details className="card card--details">
          <summary>Raw draft</summary>
          <pre>{JSON.stringify(interaction.draft, null, 2)}</pre>
        </details>
        <details className="card card--details">
          <summary>Typed semantics</summary>
          <pre>{JSON.stringify(interaction.semantics, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}

function StepEditor({
  interaction,
  onCommand,
}: {
  interaction: InteractionState;
  onCommand: (command: string) => Promise<void>;
}) {
  const step = interaction.current_step;

  if (!step) {
    return (
      <div className="empty-state compact">
        <p>Для текущего extension этот шаг редактируется через чат или не выбран.</p>
      </div>
    );
  }

  if (step.shape?.kind === "table") {
    return <TableEditor interaction={interaction} shape={step.shape} step={step} onCommand={onCommand} />;
  }

  if (step.shape?.kind === "matrix") {
    return <MatrixEditor interaction={interaction} shape={step.shape} step={step} onCommand={onCommand} />;
  }

  return <ScalarVectorEditor interaction={interaction} step={step} onCommand={onCommand} />;
}

function ScalarVectorEditor({
  interaction,
  step,
  onCommand,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  onCommand: (command: string) => Promise<void>;
}) {
  const [payload, setPayload] = useState<Record<string, unknown>>({});

  useEffect(() => {
    setPayload(initialScalarVectorPayload(interaction, step));
  }, [interaction, step]);

  return (
    <form
      className="editor-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onCommand(buildStageCommand(step.step_id, payload));
      }}
    >
      {step.scalars.map((field) => (
        <label className="field" key={field.field_path}>
          <span>{field.label}</span>
          <input
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

      <button className="primary-button" type="submit">
        Отправить шаг
      </button>
    </form>
  );
}

function TableEditor({
  interaction,
  step,
  shape,
  onCommand,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  shape: TableShapeSemantics;
  onCommand: (command: string) => Promise<void>;
}) {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    setRows(tableRows(interaction, step.step_id, shape));
  }, [interaction, shape, step.step_id]);

  return (
    <form
      className="editor-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onCommand(buildStageCommand(step.step_id, tablePayload(rows, shape)));
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
        <button className="primary-button" type="submit">
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
  onCommand,
}: {
  interaction: InteractionState;
  step: InputStepSemantics;
  shape: MatrixShapeSemantics;
  onCommand: (command: string) => Promise<void>;
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
      onSubmit={(event) => {
        event.preventDefault();
        void onCommand(buildStageCommand(step.step_id, payload));
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
      <button className="primary-button" type="submit">
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
      <div className="empty-state compact">
        <p>Результат появится здесь после команды /solve.</p>
      </div>
    );
  }

  return (
    <div className="results-stack">
      {sections.map((section) => (
        <article className="result-section" key={section.section_id}>
          <h3>{section.title}</h3>
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
    return <p className="summary-block">{block.text}</p>;
  }

  if (block.type === "kv") {
    return (
      <div className="summary-grid">
        {block.items.map((item) => (
          <div className="summary-card" key={item.key}>
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
          <div className="result-table__row" key={rowIndex}>
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
