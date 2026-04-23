import { buildStageCommand } from "@/lib/interaction";
import type { InteractionState, SlashCommandSpec } from "@/lib/types";

export type QuickActionName =
  | "show_steps"
  | "show_draft"
  | "show_result"
  | "solve"
  | "explain"
  | "help"
  | "guided_mode"
  | "power_mode";

export function buildQuickActionMessage(action: QuickActionName): string {
  switch (action) {
    case "show_steps":
      return "/show steps";
    case "show_draft":
      return "/show draft";
    case "show_result":
      return "/show result";
    case "solve":
      return "/solve";
    case "explain":
      return "/explain";
    case "help":
      return "/help";
    case "guided_mode":
      return "/mode guided";
    case "power_mode":
      return "/mode power";
  }
}

export function buildPowerCommandMessage(
  command: SlashCommandSpec,
  interaction: InteractionState,
  selectedAlias: string,
): string {
  if (command.name === "/show") {
    return "/show steps";
  }
  if (command.name === "/new") {
    return `/new ${interaction.active_extension}`;
  }
  if (command.name === "/use") {
    return `/use ${selectedAlias}`;
  }
  if (command.name === "/step" && interaction.current_stage) {
    return `/step ${interaction.current_stage}`;
  }
  if (command.name === "/payload" && interaction.current_stage) {
    const payload = interaction.expected_payload ?? {};
    return buildStageCommand(interaction.current_stage, payload);
  }
  if (command.name === "/mode") {
    return interaction.interaction_mode === "guided" ? "/mode power" : "/mode guided";
  }
  return command.name;
}
