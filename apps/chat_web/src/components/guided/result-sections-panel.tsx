"use client";

import type { DisplayBlock, ResultSection } from "@/lib/types";

type ResultSectionsPanelProps = {
  sections: ResultSection[];
};

export function ResultSectionsPanel({ sections }: ResultSectionsPanelProps) {
  if (sections.length === 0) {
    return (
      <div className="empty-state compact" data-testid="empty-result-state">
        <p>Результат появится здесь после кнопки «Решить» или команды /solve.</p>
      </div>
    );
  }

  return (
    <div className="results-stack" data-testid="results-stack">
      {sections.map((section) => (
        <article className="result-section" key={section.section_id}>
          <h3 data-testid="result-section-title">{section.title}</h3>
          {section.blocks.map((block, index) => (
            <ResultBlockView block={block} key={`${section.section_id}:${index}`} />
          ))}
        </article>
      ))}
    </div>
  );
}

function ResultBlockView({ block }: { block: DisplayBlock }) {
  if (block.type === "summary") {
    return (
      <p className="summary-block" data-testid="result-summary-block">
        {block.text}
      </p>
    );
  }

  if (block.type === "kv") {
    return (
      <div className="summary-grid">
        {block.items.map((item) => (
          <div className="summary-card" data-testid="result-kv-card" key={item.key}>
            <span>{item.key}</span>
            <strong>{String(item.value)}</strong>
          </div>
        ))}
      </div>
    );
  }

  if (block.type === "table") {
    return (
      <div className="result-table">
        <div className="result-table__row result-table__row--header">
          {block.columns.map((column) => (
            <strong key={column}>{column}</strong>
          ))}
        </div>
        {block.rows.map((row, rowIndex) => (
          <div className="result-table__row" data-testid="result-table-row" key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <span key={`${rowIndex}:${cellIndex}`}>{String(cell)}</span>
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (block.type === "list") {
    return (
      <ul className="result-list">
        {block.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
  }

  return <pre>{JSON.stringify(block.value, null, 2)}</pre>;
}
