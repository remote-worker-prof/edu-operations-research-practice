import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GuidedPanel } from "@/components/guided-panel";
import type { InteractionState } from "@/lib/types";

function transportationInteraction(): InteractionState {
  return {
    thread_id: "thread-1",
    thread_exists: true,
    active_extension: "transportation",
    available_extensions: [
      {
        alias: "study_planner",
        title: "План учёбы",
        description: "Распределение часов по темам.",
      },
      {
        alias: "transportation",
        title: "Транспортная задача",
        description: "Матрица перевозок между складами и магазинами.",
      },
    ],
    current_stage: "costs",
    pending_question: "Заполните матрицу стоимостей.",
    draft_summary: "Готово 2 из 4 этапов.",
    expected_payload: {
      cost: [
        [0, 0],
        [0, 0],
      ],
    },
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
    stage_statuses: [
      {
        stage_id: "origins",
        label: "Склады",
        depends_on: [],
        ready: true,
        current: false,
        missing: false,
        errors: [],
        expectation_hint: "Введите список складов и их запасы.",
      },
      {
        stage_id: "destinations",
        label: "Магазины",
        depends_on: ["origins"],
        ready: true,
        current: false,
        missing: false,
        errors: [],
        expectation_hint: "Введите список магазинов и их спрос.",
      },
      {
        stage_id: "costs",
        label: "Стоимость перевозки",
        depends_on: ["origins", "destinations"],
        ready: false,
        current: true,
        missing: true,
        errors: [],
        expectation_hint: "Введите матрицу стоимостей.",
      },
    ],
    current_step: {
      step_id: "costs",
      label: "Стоимость перевозки",
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
            label: "Матрица стоимости",
            value_type: "number",
            required: true,
          },
        ],
      },
      example_command: '/payload costs {"cost":[[4,7],[6,5]]}',
    },
    display: {
      summary: [],
      tables: [],
      matrices: [],
    },
    result_sections: [],
    commands: [
      {
        name: "/show",
        usage: "/show [steps|draft|result]",
        summary: "Показать текущий статус.",
        category: "user",
      },
      {
        name: "/solve",
        usage: "/solve",
        summary: "Запустить расчёт.",
        category: "user",
      },
      {
        name: "/payload",
        usage: "/payload <stage> <json>",
        summary: "Отправить structured payload.",
        category: "power",
      },
    ],
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
        {
          step_id: "costs",
          label: "Стоимость перевозки",
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
                label: "Матрица стоимости",
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

describe("GuidedPanel", () => {
  it("renders matrix editor labels from typed semantics", () => {
    render(
      <GuidedPanel
        interaction={transportationInteraction()}
        onMessage={vi.fn().mockResolvedValue(undefined)}
        onCreateThread={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "Транспортная задача" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Склад 1")).toBeInTheDocument();
    expect(screen.getByText("Магазин 2")).toBeInTheDocument();
    expect(screen.getByText("Матрица стоимости")).toBeInTheDocument();
  });

  it("submits matrix payloads as slash commands", async () => {
    const onMessage = vi.fn().mockResolvedValue(undefined);

    render(
      <GuidedPanel
        interaction={transportationInteraction()}
        onMessage={onMessage}
        onCreateThread={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const inputs = screen.getAllByRole("spinbutton");
    fireEvent.change(inputs[0], { target: { value: "11" } });
    fireEvent.change(inputs[1], { target: { value: "12" } });
    fireEvent.change(inputs[2], { target: { value: "13" } });
    fireEvent.change(inputs[3], { target: { value: "14" } });

    fireEvent.click(screen.getByRole("button", { name: "Отправить матрицу" }));

    await waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith(
        '/payload costs {"cost":[[11,12],[13,14]]}',
      );
    });
  });

  it("maps quick actions to canonical slash commands", async () => {
    const onMessage = vi.fn().mockResolvedValue(undefined);

    render(
      <GuidedPanel
        interaction={transportationInteraction()}
        onMessage={onMessage}
        onCreateThread={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    fireEvent.click(screen.getByTestId("show-steps-button"));

    await waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith("/show steps");
    });
  });

  it("sends freeform power-mode messages through the same backend hook", async () => {
    const onMessage = vi.fn().mockResolvedValue(undefined);

    render(
      <GuidedPanel
        interaction={transportationInteraction()}
        onMessage={onMessage}
        onCreateThread={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    fireEvent.click(screen.getByText("Режим преподавателя и команды"));
    fireEvent.change(screen.getByTestId("power-console-input"), {
      target: { value: "Покажи состояние текущего треда." },
    });
    fireEvent.click(screen.getByTestId("power-console-send"));

    await waitFor(() => {
      expect(onMessage).toHaveBeenCalledWith("Покажи состояние текущего треда.");
    });
  });
});
