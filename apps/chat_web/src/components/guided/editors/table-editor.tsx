"use client";

import { buildStageCommand, tablePayload, tableRows } from "@/lib/interaction";
import type { InteractionState, TableShapeSemantics } from "@/lib/types";
import { useStepPayloadState } from "@/components/guided/use-step-payload-state";

type TableEditorProps = {
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
  shape: TableShapeSemantics;
  stepId: string;
};

export function TableEditor({
  interaction,
  onMessage,
  shape,
  stepId,
}: TableEditorProps) {
  const [rows, setRows] = useStepPayloadState(
    () => tableRows(interaction, stepId, shape),
    [interaction, shape, stepId],
  );

  return (
    <form
      className="editor-form"
      data-testid={`table-editor-${stepId}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onMessage(buildStageCommand(stepId, tablePayload(rows, shape)));
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
              data-testid={`table-${stepId}-${rowIndex}-${shape.key.field_path}`}
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
                data-testid={`table-${stepId}-${rowIndex}-${column.field_path}`}
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
          data-testid={`add-row-${stepId}`}
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
          data-testid={`submit-step-${stepId}`}
          type="submit"
        >
          Отправить таблицу
        </button>
      </div>
    </form>
  );
}
