import { useMemo } from 'react';
import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';
import { operationsKpis } from '../api/kpi';

export function Operations() {
  const recs = useApi(() => api.recommendations(), 60_000);
  const approvals = useApi(() => api.approvals(), 60_000);
  const outcomes = useApi(() => api.outcomes(), 60_000);

  const kpis = useMemo(
    () => operationsKpis(recs.data ?? [], approvals.data ?? [], outcomes.data ?? []),
    [recs.data, approvals.data, outcomes.data],
  );

  return (
    <div className="view-grid">
      <ErrorBoundary label="Production impact">
        <Card title="Active intervention impact">
          <ul className="action-metrics">
            <li>Approved interventions: <strong>{kpis.approvedCount}</strong></li>
            <li>Cumulative tonnes delayed: <strong>{kpis.tonnesDelayed.toFixed(0)}</strong></li>
            <li>Avg intervention effectiveness: <strong>{(kpis.avgEffectiveness * 100).toFixed(0)}%</strong></li>
          </ul>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Tonnes protected">
        <Card title="Tonnes protected" subtitle="Effectiveness-weighted">
          <div className="big-metric">
            <span className="value">{kpis.tonnesProtected.toFixed(0)}</span>
            <span className="unit">tonnes</span>
          </div>
          <p className="muted">Estimate from approved interventions × measured effectiveness.</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Shutdowns avoided">
        <Card title="Shutdowns avoided">
          <div className="big-metric">
            <span className="value">{kpis.shutdownsAvoided}</span>
            <span className="unit">approved</span>
          </div>
          <p className="muted">Each approval represents an action taken to keep production running.</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="ROI estimate">
        <Card title="ROI estimate (rough)">
          <p className="muted">
            Shadow-mode ROI uses tonnes-protected × tonne-margin from site_config.cost_curves.
            Cost curves not yet populated; full ROI lands in Phase K.
          </p>
        </Card>
      </ErrorBoundary>
    </div>
  );
}
