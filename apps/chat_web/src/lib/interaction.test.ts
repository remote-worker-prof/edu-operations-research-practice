import { describe, expect, it } from "vitest";

import {
  buildStageCommand,
  getSetMembers,
  initialMatrixPayload,
  initialScalarVectorPayload,
  tablePayload,
  tableRows,
  vectorLabels,
} from "@/lib/interaction";
import type { InteractionState } from "@/lib/types";

function baseInteraction(): InteractionState {
  return {
    thread_id: "thread-1",
    thread_exists: true,
    active_extension: "transportation",
    available_extensions: [
      {
        alias: "transportation",
        title: "Транспортная задача",
        description: "Распределение между складами и магазинами.",
      },
    ],
    current_stage: "costs",
    pending_question: "Введите матрицу стоимостей.",
    draft_summary: "Готово 2 из 4 этапов.",
    expected_payload: { cost: [[0, 0], [0, 0]] },
    draft: {
      origins: {
        origin: ["Склад 1", "Склад 2"],
        supply: [30, 40],
      },
      destinations: {
        destination: ["Магазин 1", "Магазин 2"],
        demand: [35, 35],
      },
      costs: {
        cost: [
          [4, 7],
          [6, 5],
        ],
      },
    },
    stage_statuses: [],
    current_step: {
      step_id: "costs",
      label: "Матрица стоимостей",
      scalars: [],
      vectors: [],
      shape: {
        kind: "matrix",
        row_set: "ORIGINS",
        col_set: "DESTINATIONS",
        fields: [
          {
            kind: "matrix_field",
            param: "cost",
            row_set: "ORIGINS",
            col_set: "DESTINATIONS",
            field_path: "cost",
            label: "Стоимость перевозки",
            value_type: "number",
            required: true,
          },
        ],
      },
    },
    display: null,
    result_sections: [],
    commands: [],
    semantics: {
      supported: true,
      mode: "declarative_bundle",
      alias: "transportation",
      dsl_format: "student_math_v2",
      wizard_mode: "linear",
      stage_ids: ["origins", "destinations", "costs"],
      display: {
        summary: [],
        tables: [],
        matrices: [],
      },
      inputs: [
        {
          step_id: "origins",
          label: "Склады",
          scalars: [],
          vectors: [],
          shape: {
            kind: "table",
            set_name: "ORIGINS",
            key: {
              kind: "table_key",
              set_name: "ORIGINS",
              field_path: "origin",
              label: "Склад",
            },
            columns: [
              {
                kind: "table_column",
                param: "supply",
                set_name: "ORIGINS",
                field_path: "supply",
                label: "Запас",
                value_type: "number",
                required: true,
              },
            ],
          },
        },
        {
          step_id: "destinations",
          label: "Магазины",
          scalars: [],
          vectors: [],
          shape: {
            kind: "table",
            set_name: "DESTINATIONS",
            key: {
              kind: "table_key",
              set_name: "DESTINATIONS",
              field_path: "destination",
              label: "Магазин",
            },
            columns: [
              {
                kind: "table_column",
                param: "demand",
                set_name: "DESTINATIONS",
                field_path: "demand",
                label: "Спрос",
                value_type: "number",
                required: true,
              },
            ],
          },
        },
      ],
    },
  };
}

describe("interaction helpers", () => {
  it("extracts set members from semantics-backed draft tables", () => {
    const interaction = baseInteraction();

    expect(getSetMembers(interaction, "ORIGINS")).toEqual(["Склад 1", "Склад 2"]);
    expect(vectorLabels(interaction, { ...interaction.semantics!.inputs[0].shape!.columns[0], kind: "vector", over: "ORIGINS" })).toEqual([
      "Склад 1",
      "Склад 2",
    ]);
  });

  it("builds stable scalar/vector and matrix payloads", () => {
    const interaction = baseInteraction();
    const scalarStep = {
      step_id: "budget",
      label: "Бюджет",
      scalars: [
        {
          kind: "scalar" as const,
          param: "available_hours",
          field_path: "available_hours",
          label: "Часы",
          value_type: "number" as const,
          required: true,
        },
      ],
      vectors: [
        {
          kind: "vector" as const,
          param: "priority",
          over: "ORIGINS",
          field_path: "priority",
          label: "Приоритет",
          value_type: "number" as const,
          required: true,
        },
      ],
      shape: null,
    };

    interaction.draft.budget = { available_hours: 12, priority: [9, 8] };

    expect(initialScalarVectorPayload(interaction, scalarStep)).toEqual({
      available_hours: 12,
      priority: [9, 8],
    });

    expect(
      initialMatrixPayload(
        interaction,
        "costs",
        interaction.current_step!.shape as NonNullable<typeof interaction.current_step>["shape"] & {
          kind: "matrix";
        },
      ),
    ).toEqual({
      cost: [
        [4, 7],
        [6, 5],
      ],
    });
  });

  it("converts row editors into payloads and slash commands", () => {
    const interaction = baseInteraction();
    const tableShape = interaction.semantics!.inputs[0].shape;
    if (!tableShape || tableShape.kind !== "table") {
      throw new Error("expected table shape");
    }

    expect(tableRows(interaction, "origins", tableShape)).toEqual([
      { origin: "Склад 1", supply: 30 },
      { origin: "Склад 2", supply: 40 },
    ]);

    const payload = tablePayload(
      [
        { origin: "Склад A", supply: 15 },
        { origin: "Склад B", supply: 25 },
      ],
      tableShape,
    );

    expect(payload).toEqual({
      origin: ["Склад A", "Склад B"],
      supply: [15, 25],
    });
    expect(buildStageCommand("origins", payload)).toBe(
      '/payload origins {"origin":["Склад A","Склад B"],"supply":[15,25]}',
    );
  });
});
