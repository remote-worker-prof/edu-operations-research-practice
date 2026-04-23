"use client";

import type { StageInteraction } from "@/lib/types";

type StageListPanelProps = {
  onSelectStage: (stageId: string) => void;
  pendingQuestion?: string | null;
  stages: StageInteraction[];
};

export function StageListPanel({
  onSelectStage,
  pendingQuestion,
  stages,
}: StageListPanelProps) {
  return (
    <section className="card">
      <div className="card__header">
        <h2>Этапы</h2>
        <p>{pendingQuestion}</p>
      </div>
      <div className="stage-list">
        {stages.map((stage) => (
          <button
            className={`stage-tile${stage.current ? " stage-tile--current" : ""}${
              stage.ready ? " stage-tile--ready" : ""
            }`}
            data-testid={`stage-tile-${stage.stage_id}`}
            key={stage.stage_id}
            onClick={() => onSelectStage(stage.stage_id)}
            type="button"
          >
            <div className="stage-tile__head">
              <strong>{stage.label}</strong>
              <span>{stage.ready ? "готово" : "ожидает"}</span>
            </div>
            <p>{stage.expectation_hint}</p>
            {stage.errors.map((error) => (
              <small key={error}>{error}</small>
            ))}
          </button>
        ))}
      </div>
    </section>
  );
}
