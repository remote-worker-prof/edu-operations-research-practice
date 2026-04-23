"use client";

import { type ReactNode, useMemo } from "react";

import { buildStageCommand, getSetMembers, initialMatrixPayload } from "@/lib/interaction";
import type { InteractionState, MatrixShapeSemantics } from "@/lib/types";
import { useStepPayloadState } from "@/components/guided/use-step-payload-state";

type MatrixEditorProps = {
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
  shape: MatrixShapeSemantics;
  stepId: string;
};

export function MatrixEditor({
  interaction,
  onMessage,
  shape,
  stepId,
}: MatrixEditorProps) {
  const [payload, setPayload] = useStepPayloadState(
    () => initialMatrixPayload(interaction, stepId, shape),
    [interaction, shape, stepId],
  );

  const rowLabels = useMemo(
    () => getSetMembers(interaction, shape.row_set),
    [interaction, shape.row_set],
  );
  const colLabels = useMemo(
    () => getSetMembers(interaction, shape.col_set),
    [interaction, shape.col_set],
  );

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
      data-testid={`matrix-editor-${stepId}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onMessage(buildStageCommand(stepId, payload));
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
                    data-testid={`matrix-${stepId}-${field.field_path}-${rowIndex}-${colIndex}`}
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
        data-testid={`submit-step-${stepId}`}
        type="submit"
      >
        Отправить матрицу
      </button>
    </form>
  );
}

function FragmentRow({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <>
      <strong>{label}</strong>
      {children}
    </>
  );
}
