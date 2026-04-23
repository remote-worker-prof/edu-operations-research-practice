"use client";

import { useEffect, useState } from "react";

import { ChatHero } from "@/components/guided/chat-hero";
import { PendingProposalsCard } from "@/components/guided/pending-proposals-card";
import { PowerConsolePanel } from "@/components/guided/power-console-panel";
import { QuickActionsBar } from "@/components/guided/quick-actions-bar";
import { ResultSectionsPanel } from "@/components/guided/result-sections-panel";
import { StageListPanel } from "@/components/guided/stage-list-panel";
import { StepEditorPanel } from "@/components/guided/step-editor-panel";
import { useGuidedCommands } from "@/components/guided/use-guided-commands";
import type { InteractionState } from "@/lib/types";

type GuidedPanelShellProps = {
  interaction: InteractionState;
  onCreateThread: (extensionAlias?: string) => Promise<void>;
  onMessage: (message: string) => Promise<void>;
};

export function GuidedPanelShell({
  interaction,
  onCreateThread,
  onMessage,
}: GuidedPanelShellProps) {
  const [selectedAlias, setSelectedAlias] = useState<string>("study_planner");

  useEffect(() => {
    if (interaction.active_extension) {
      setSelectedAlias(interaction.active_extension);
    }
  }, [interaction.active_extension]);

  const activeExtension = interaction.available_extensions.find(
    (item) => item.alias === interaction.active_extension,
  );
  const commands = useGuidedCommands({
    interaction,
    onCreateThread,
    onMessage,
    selectedAlias,
  });

  return (
    <section className="guided-panel" data-testid="guided-panel">
      <ChatHero
        activeDescription={activeExtension?.description}
        activeTitle={activeExtension?.title ?? interaction.active_extension}
        availableExtensions={interaction.available_extensions}
        onCreateThread={() => void commands.createThread()}
        onResetThread={() => void commands.resetThread()}
        onSwitchExtension={() => void commands.switchExtension()}
        selectedAlias={selectedAlias}
        setSelectedAlias={setSelectedAlias}
      />

      <div className="status-strip" data-testid="status-strip">
        <div>
          <span className="status-strip__label">Текущий шаг</span>
          <strong data-testid="current-stage-value">
            {interaction.current_stage ?? "не выбран"}
          </strong>
        </div>
        <div>
          <span className="status-strip__label">Сводка</span>
          <strong data-testid="draft-summary-value">{interaction.draft_summary}</strong>
        </div>
        <div>
          <span className="status-strip__label">Режим</span>
          <strong data-testid="interaction-mode-value">
            {interaction.interaction_mode === "power" ? "power" : "guided"}
          </strong>
        </div>
      </div>

      <QuickActionsBar
        onExplain={() => void commands.sendQuickAction("explain")}
        onGuidedMode={() => void commands.sendQuickAction("guided_mode")}
        onHelp={() => void commands.sendQuickAction("help")}
        onPowerMode={() => void commands.sendQuickAction("power_mode")}
        onShowDraft={() => void commands.sendQuickAction("show_draft")}
        onShowResult={() => void commands.sendQuickAction("show_result")}
        onShowSteps={() => void commands.sendQuickAction("show_steps")}
        onSolve={() => void commands.sendQuickAction("solve")}
      />

      <PendingProposalsCard
        onConfirm={() => void onMessage("да")}
        onReject={() => void onMessage("нет")}
        proposals={interaction.pending_proposals}
      />

      <div className="workspace-grid">
        <StageListPanel
          onSelectStage={(stageId) => void onMessage(`/step ${stageId}`)}
          pendingQuestion={interaction.pending_question}
          stages={interaction.stage_statuses}
        />

        <section className="card">
          <div className="card__header">
            <h2>Ввод данных</h2>
            <p>
              Рабочая форма строится автоматически из typed semantics текущего
              extension.
            </p>
          </div>
          <StepEditorPanel interaction={interaction} onMessage={onMessage} />
        </section>

        <section className="card">
          <div className="card__header">
            <h2>Результаты</h2>
            <p>
              Здесь показываются те же result blocks, которые backend уже
              строит для deterministic runtime.
            </p>
          </div>
          <ResultSectionsPanel sections={interaction.result_sections} />
        </section>
      </div>

      <div className="details-grid">
        <PowerConsolePanel
          commandButtons={interaction.commands.map((command) => (
            <button
              className={`command-pill command-pill--${command.category}`}
              key={command.name}
              onClick={() => void commands.sendPowerCommand(command)}
              type="button"
            >
              <strong>{command.name}</strong>
              <span>{command.summary}</span>
            </button>
          ))}
          currentStage={interaction.current_stage ?? null}
          examplePayload={interaction.expected_payload ?? null}
          interaction={interaction}
          onMessage={onMessage}
        />
      </div>
    </section>
  );
}
