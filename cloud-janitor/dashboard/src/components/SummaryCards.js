import React from 'react';

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value || 0);

const cardDefinitions = (report) => [
  { label: 'Total Resources Scanned', value: report?.totalResources || 0 },
  { label: '✅ Healthy', value: report?.bandSummary?.healthy || 0 },
  { label: '⚠️ Warning', value: report?.bandSummary?.warning || 0 },
  { label: '🔶 Cleanup Candidate', value: report?.bandSummary?.cleanupCandidate || 0 },
  { label: '🔴 Delete Candidate', value: report?.bandSummary?.deleteCandidate || 0 },
  { label: '💰 Estimated Monthly Savings', value: formatCurrency(report?.estimatedMonthlySavings || 0) },
];

function SummaryCards({ report }) {
  return (
    <section className="cards-grid">
      {cardDefinitions(report).map((card) => (
        <div className="summary-card" key={card.label}>
          <div className="label">{card.label}</div>
          <div className="value">{card.value}</div>
        </div>
      ))}
    </section>
  );
}

export default SummaryCards;
