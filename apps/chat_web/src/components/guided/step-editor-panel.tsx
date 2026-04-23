"use client";

import { MatrixEditor } from "@/components/guided/editors/matrix-editor";
import { ScalarVectorEditor } from "@/components/guided/editors/scalar-vector-editor";
import { TableEditor } from "@/components/guided/editors/table-editor";
import type { InteractionState } from "@/lib/types";

type StepEditorPanelProps = {
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
};

export function StepEditorPanel({
  interaction,
  onMessage,
}: StepEditorPanelProps) {
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
        stepId={step.step_id}
      />
    );
  }

  if (step.shape?.kind === "matrix") {
    return (
      <MatrixEditor
        interaction={interaction}
        onMessage={onMessage}
        shape={step.shape}
        stepId={step.step_id}
      />
    );
  }

  return (
    <ScalarVectorEditor
      interaction={interaction}
      onMessage={onMessage}
      step={step}
    />
  );
}
