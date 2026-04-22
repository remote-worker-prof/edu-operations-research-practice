import type {
  InputStepSemantics,
  InteractionState,
  MatrixShapeSemantics,
  TableShapeSemantics,
  VectorFieldSemantics,
} from "@/lib/types";

export function getSetMembers(
  interaction: InteractionState,
  setName: string,
): string[] {
  const sourceStep = interaction.semantics?.inputs.find((step) => {
    return step.shape?.kind === "table" && step.shape.set_name === setName;
  });
  if (!sourceStep || !sourceStep.shape || sourceStep.shape.kind !== "table") {
    return [];
  }
  const stageDraft = interaction.draft[sourceStep.step_id] ?? {};
  const raw = stageDraft[sourceStep.shape.key.field_path];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((value) => String(value));
}

export function buildStageCommand(
  stageId: string,
  payload: Record<string, unknown>,
): string {
  return `/payload ${stageId} ${JSON.stringify(payload)}`;
}

export function initialScalarVectorPayload(
  interaction: InteractionState,
  step: InputStepSemantics,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const scalar of step.scalars) {
    payload[scalar.field_path] = interaction.draft[step.step_id]?.[scalar.field_path] ?? 0;
  }
  for (const vector of step.vectors) {
    const fromDraft = interaction.draft[step.step_id]?.[vector.field_path];
    if (Array.isArray(fromDraft)) {
      payload[vector.field_path] = fromDraft;
      continue;
    }
    const size = Math.max(getSetMembers(interaction, vector.over).length, 1);
    payload[vector.field_path] = Array.from({ length: size }, () => 0);
  }
  return payload;
}

export function tableRows(
  interaction: InteractionState,
  stepId: string,
  shape: TableShapeSemantics,
): Array<Record<string, unknown>> {
  const draft = interaction.draft[stepId] ?? {};
  const keys = Array.isArray(draft[shape.key.field_path])
    ? (draft[shape.key.field_path] as unknown[])
    : [];
  const rowCount = Math.max(keys.length, 2);
  return Array.from({ length: rowCount }, (_, index) => {
    const row: Record<string, unknown> = {
      [shape.key.field_path]: keys[index] ?? "",
    };
    for (const column of shape.columns) {
      const values = Array.isArray(draft[column.field_path])
        ? (draft[column.field_path] as unknown[])
        : [];
      row[column.field_path] = values[index] ?? 0;
    }
    return row;
  });
}

export function tablePayload(
  rows: Array<Record<string, unknown>>,
  shape: TableShapeSemantics,
): Record<string, unknown> {
  const payload: Record<string, unknown[]> = {
    [shape.key.field_path]: [],
  };
  for (const column of shape.columns) {
    payload[column.field_path] = [];
  }
  for (const row of rows) {
    payload[shape.key.field_path].push(row[shape.key.field_path] ?? "");
    for (const column of shape.columns) {
      payload[column.field_path].push(row[column.field_path] ?? 0);
    }
  }
  return payload;
}

export function initialMatrixPayload(
  interaction: InteractionState,
  stepId: string,
  shape: MatrixShapeSemantics,
): Record<string, number[][]> {
  const rowCount = Math.max(getSetMembers(interaction, shape.row_set).length, 1);
  const colCount = Math.max(getSetMembers(interaction, shape.col_set).length, 1);
  const draft = interaction.draft[stepId] ?? {};
  const payload: Record<string, number[][]> = {};
  for (const field of shape.fields) {
    const current = draft[field.field_path];
    if (Array.isArray(current)) {
      payload[field.field_path] = current as number[][];
      continue;
    }
    payload[field.field_path] = Array.from({ length: rowCount }, () =>
      Array.from({ length: colCount }, () => 0),
    );
  }
  return payload;
}

export function vectorLabels(
  interaction: InteractionState,
  field: VectorFieldSemantics,
): string[] {
  return getSetMembers(interaction, field.over);
}
