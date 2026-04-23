"use client";

import type { PatchProposal } from "@/lib/types";

type PendingProposalsCardProps = {
  onConfirm: () => void;
  onReject: () => void;
  proposals: PatchProposal[];
};

export function PendingProposalsCard({
  onConfirm,
  onReject,
  proposals,
}: PendingProposalsCardProps) {
  if (proposals.length === 0) {
    return null;
  }

  return (
    <section className="card" data-testid="pending-proposals-card">
      <div className="card__header">
        <h2>Ожидают подтверждения</h2>
        <p>
          Ассистент предложил обновления для текущего черновика. Можно
          принять или отклонить их одной кнопкой.
        </p>
      </div>
      <div className="proposal-list">
        {proposals.map((proposal, index) => (
          <div
            className="proposal-item"
            data-testid={`proposal-item-${index}`}
            key={`${proposal.stage_id}:${proposal.path ?? "payload"}:${index}`}
          >
            <strong>{proposal.stage_id}</strong>
            <pre>
              {proposal.payload
                ? JSON.stringify(proposal.payload, null, 2)
                : `${proposal.path} = ${JSON.stringify(proposal.value)}`}
            </pre>
          </div>
        ))}
      </div>
      <div className="hero__actions">
        <button
          className="primary-button"
          data-testid="confirm-proposals-button"
          onClick={onConfirm}
          type="button"
        >
          Применить
        </button>
        <button
          className="ghost-button"
          data-testid="reject-proposals-button"
          onClick={onReject}
          type="button"
        >
          Отклонить
        </button>
      </div>
    </section>
  );
}
