import React, { useEffect, useState } from 'react';
import SummaryCards from './components/SummaryCards';
import ResourceTable from './components/ResourceTable';

const sampleReport = {
  dryRun: true,
  generatedAt: '2026-07-20T00:00:00Z',
  subscriptionIds: ['sample-subscription'],
  totalResources: 2,
  bandSummary: {
    healthy: 1,
    warning: 0,
    cleanupCandidate: 1,
    deleteCandidate: 0,
  },
  estimatedMonthlySavings: 125.5,
  topWasteByOwner: [{ owner: 'demo-owner', totalCost: 125.5, resourceCount: 1 }],
  resources: [
    {
      id: '1',
      name: 'demo-vm',
      type: 'Microsoft.Compute/virtualMachines',
      resourceGroup: 'rg-demo',
      region: 'eastus',
      tags: { owner: 'demo-owner' },
      score: 60,
      band: 'Cleanup Candidate',
      cost: 125.5,
      reasons: ['idle based on resource metrics or attachment state', 'missing backup policy'],
    },
    {
      id: '2',
      name: 'demo-storage',
      type: 'Microsoft.Storage/storageAccounts',
      resourceGroup: 'rg-demo',
      region: 'eastus2',
      tags: { owner: 'platform' },
      score: 5,
      band: 'Healthy',
      cost: 42,
      reasons: [],
    },
  ],
  humanSummary: 'Sample dry-run report shown because /api/report could not be loaded.',
};

function App() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    fetch('/api/report')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        if (!active) {
          return;
        }
        setReport(data);
      })
      .catch((err) => {
        if (!active) {
          return;
        }
        setError(`Using bundled sample report because live report fetch failed: ${err.message}`);
        setReport(sampleReport);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div className="loading">Loading Cloud Janitor report...</div>;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>☁️ Cloud Janitor Dashboard — Phase 1 (Dry Run Only)</h1>
          <p>{report?.humanSummary}</p>
        </div>
        <div className="header-meta">
          <span className="pill">Dry Run Only</span>
          <span className="generated-at">
            Generated: {report?.generatedAt ? new Date(report.generatedAt).toLocaleString() : 'N/A'}
          </span>
        </div>
      </header>

      {error ? <div className="notice">{error}</div> : null}

      <SummaryCards report={report} />
      <ResourceTable resources={report?.resources || []} />
    </div>
  );
}

export default App;
