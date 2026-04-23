"use client";

import { useMemo } from "react";

import {
  buildPowerCommandMessage,
  buildQuickActionMessage,
  type QuickActionName,
} from "@/components/guided/command-builders";
import type { InteractionState, SlashCommandSpec } from "@/lib/types";

type GuidedCommandOptions = {
  interaction: InteractionState;
  onCreateThread: (extensionAlias?: string) => Promise<void>;
  onMessage: (message: string) => Promise<void>;
  selectedAlias: string;
};

export function useGuidedCommands({
  interaction,
  onCreateThread,
  onMessage,
  selectedAlias,
}: GuidedCommandOptions) {
  return useMemo(
    () => ({
      createThread: () => onCreateThread(selectedAlias),
      switchExtension: () => onMessage(`/use ${selectedAlias}`),
      resetThread: () => onMessage("/reset"),
      sendQuickAction: (action: QuickActionName) =>
        onMessage(buildQuickActionMessage(action)),
      sendPowerCommand: (command: SlashCommandSpec) =>
        onMessage(buildPowerCommandMessage(command, interaction, selectedAlias)),
    }),
    [interaction, onCreateThread, onMessage, selectedAlias],
  );
}
