"use client";

import { buildStageCommand, initialScalarVectorPayload, vectorLabels } from "@/lib/interaction";
import type { InputStepSemantics, InteractionState } from "@/lib/types";
import { useStepPayloadState } from "@/components/guided/use-step-payload-state";

type ScalarVectorEditorProps = {
  interaction: InteractionState;
  onMessage: (message: string) => Promise<void>;
  step: InputStepSemantics;
};

export function ScalarVectorEditor({
  interaction,
  onMessage,
  step,
}: ScalarVectorEditorProps) {
  const [payload, setPayload] = useStepPayloadState(
    () => initialScalarVectorPayload(interaction, step),
    [interaction, step],
  );

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
                        const next = [
                          ...(Array.isArray(current[field.field_path])
                            ? (current[field.field_path] as unknown[])
                            : values),
                        ];
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
