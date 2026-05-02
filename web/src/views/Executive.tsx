import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';

export function Executive() {
  const approvals = useApi(() => api.approvals(), [], 60_000);
  const events = useApi(() => api.dustEvents(), [], 60_000);
  const outcomes = useApi(() => api.outcomes(), [], 60_000);

  const approvedCount = (approvals.data ?? []).filter(a => a.approval_status === 'approved').length;
  const overrideCount = (approvals.data ?? []).filter(a => a.approval_status === 'overridden').length;
  const eventCount = events.data?.length ?? 0;
  const incidentsAvoided = approvedCount + overrideCount;
  const avgEff = outcomes.data?.length
    ? outcomes.data.reduce((s, o) => s + o.intervention_effectiveness, 0) / outcomes.data.length
    : 0;

  return (
    <div className="view-grid">
      <ErrorBoundary label="Downtime avoided">
        <Card title="Downtime avoided (rolling)">
          <div className="big-metric">
            <span className="value">{incidentsAvoided}</span>
            <span className="unit">decisions</span>
          </div>
          <p className="muted">Sum of approve + override decisions on dust risk recommendations.</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Compliance incidents">
        <Card title="Compliance incidents avoided">
          <div className="big-metric">
            <span className="value">{Math.max(eventCount - approvedCount, 0)}</span>
            <span className="unit">net exposure</span>
          </div>
          <p className="muted">Dust events recorded minus interventions approved.</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Effectiveness trend">
        <Card title="Intervention effectiveness">
          <div className="big-metric">
            <span className="value">{(avgEff * 100).toFixed(0)}%</span>
            <span className="unit">avg</span>
          </div>
          <p className="muted">Average across all recorded outcomes (S14 feeder).</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Environmental performance">
        <Card title="Environmental performance">
          <p className="muted">
            Trend-over-time charting lands in Phase K alongside the predicted-vs-actual join.
            The numbers above are point-in-time aggregates pulled from S13 / S14 feeds.
          </p>
        </Card>
      </ErrorBoundary>
    </div>
  );
}
