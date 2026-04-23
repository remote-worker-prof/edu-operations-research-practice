import { describe, expect, it } from "vitest";

import {
  buildPowerCommandMessage,
  buildQuickActionMessage,
} from "@/components/guided/command-builders";
import type { InteractionState, SlashCommandSpec } from "@/lib/types";

function interaction(): InteractionState {
  return {
    thread_id: "thread-1",
    thread_exists: true,
    active_extension: "transportation",
    available_extensions: [
      {
        alias: "transportation",
        title: "Транспортная задача",
        description: "Матрица перевозок.",
      },
    ],
    current_stage: "costs",
    pending_question: "Введите стоимость.",
    draft_summary: "Готово 2 из 4 этапов.",
    expected_payload: { cost_matrix: [[0, 0], [0, 0]] },
    draft: {},
    stage_statuses: [],
    current_step: null,
    display: { summary: [], tables: [], matrices: [] },
    result_sections: [],
    commands: [],
    interaction_mode: "guided",
    nl_apply_policy: "confirm",
    pending_proposals: [],
    last_intent: null,
    semantics: null,
  };
}

describe("guided command builders", () => {
  it("maps quick actions to canonical slash commands", () => {
    expect(buildQuickActionMessage("show_steps")).toBe("/show steps");
    expect(buildQuickActionMessage("power_mode")).toBe("/mode power");
  });

  it("builds payload command examples from the active interaction state", () => {
    const command: SlashCommandSpec = {
      name: "/payload",
      usage: "/payload <stage> <json>",
      summary: "Отправить payload",
      category: "power",
    };

    expect(buildPowerCommandMessage(command, interaction(), "transportation")).toBe(
      '/payload costs {"cost_matrix":[[0,0],[0,0]]}',
    );
  });
});
