import { useState } from 'react';
import { Card } from '../components/Card';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { breachProbabilityToStatus, riskClassToStatus, StatusPill } from '../components/StatusPill';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';
import { MapCard } from './MapCard';
import { SensorHealthStrip } from './SensorHealthStrip';
import { ApproveRejectOverrideModal } from './ApproveRejectOverrideModal';

export function ControlRoom() {
  const forecast = useApi(() => api.forecastsCurrent(), 30_000);
  const recommendation = useApi(() => api.recommendationsCurrent(), 30_000);
  const attributions = useApi(() => api.attributions(), 60_000);
  const mineState = useApi(() => api.mineStateCurrent().catch(() => null), 30_000);
  const sensorHealth = useApi(() => api.sensorHealth(), 60_000);
  const events = useApi(() => api.dustEvents(), 60_000);
  const [decisionMode, setDecisionMode] = useState<null | 'approve' | 'reject' | 'override'>(null);

  const f = forecast.data;
  const r = recommendation.data;
  const primaryAction = r?.recommended_actions[0] ?? null;

  return (
    <div className="view-grid view-grid-control">
      <ErrorBoundary label="Forecast">
        <Card
          title="Current dust risk"
          subtitle={f ? `${f.target_kind}:${f.target_id} · ${f.forecast_horizon}` : '—'}
          status={breachProbabilityToStatus(f?.breach_probability)}
          warnings={f?.data_quality_warnings ?? []}
        >
          {forecast.initialLoading && <p className="muted">Loading forecast…</p>}
          {forecast.error && <p className="error-row">{forecast.error.message}</p>}
          {f ? (
            <>
              <div className="big-metric">
                <span className="value">{f.predicted_pm10.toFixed(0)}</span>
                <span className="unit">µg/m³ PM10</span>
              </div>
              <div className="muted">
                PM2.5 {f.predicted_pm25.toFixed(0)} · breach prob {(f.breach_probability * 100).toFixed(0)}%
              </div>
              <ConfidenceBadge confidence={f.confidence} note={`model ${f.model_version}`} />
              <p className="reason">{f.main_risk_window}. {f.main_uncertainty}</p>
              {f.source !== 'model' && (
                <p className="muted">⚠ source: {f.source} (model fallback per G11)</p>
              )}
            </>
          ) : (
            !forecast.initialLoading && <p className="muted">No forecast available yet.</p>
          )}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Likely cause">
        <Card title="Likely cause" subtitle="Top probable sources">
          {attributions.initialLoading && <p className="muted">Loading…</p>}
          {attributions.data && attributions.data.length === 0 && <p className="muted">No attributions yet.</p>}
          {attributions.data?.slice(0, 1).map((a) => (
            <div key={a.attribution_id}>
              <ConfidenceBadge confidence={a.confidence} />
              <ol className="cause-list">
                {a.probable_sources.slice(0, 3).map((src, i) => (
                  <li key={i}>
                    <strong>{src.source}</strong>
                    <span className="muted"> · {Math.round(src.confidence * 100)}% conf</span>
                    <div className="reason">{src.reason}</div>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Recommended action">
        <Card
          title="Recommended action"
          subtitle={r ? r.recommendation_id : '—'}
          warnings={r?.requires_human_review ? ['Human review required (low confidence or high risk)'] : []}
          actions={r && primaryAction && (
            <>
              <button
                className="btn-approve"
                onClick={() => setDecisionMode('approve')}
                disabled={primaryAction.requires_human_approval}
                title={primaryAction.requires_human_approval ? 'G1: this action requires human approval — use Override or Reject' : ''}
              >
                Approve
              </button>
              <button className="btn-reject" onClick={() => setDecisionMode('reject')}>Reject</button>
              <button className="btn-override" onClick={() => setDecisionMode('override')}>Override</button>
            </>
          )}
        >
          {recommendation.initialLoading && <p className="muted">Loading…</p>}
          {!r && !recommendation.initialLoading && <p className="muted">No active recommendation.</p>}
          {r && primaryAction && (
            <>
              <div className="action-headline">
                <StatusPill status={riskClassToStatus(primaryAction.risk_class)} label={primaryAction.risk_class.toUpperCase()} />
                <strong>{primaryAction.action}</strong>
              </div>
              <ul className="action-metrics">
                <li>Breach prob after: <strong>{(primaryAction.breach_probability_after * 100).toFixed(0)}%</strong></li>
                <li>Tonnes delayed: <strong>{primaryAction.estimated_tonnes_delayed.toFixed(0)}</strong></li>
                <li>Production loss: <strong>{primaryAction.production_loss}</strong></li>
                <li>Intervention: <code>{primaryAction.intervention_id}</code></li>
              </ul>
              <ConfidenceBadge confidence={r.confidence} note={r.compliance_priority_triggered ? 'compliance priority' : undefined} />
              <p className="reason">{r.reason}</p>
              {r.recommended_actions.length > 1 && (
                <details>
                  <summary>{r.recommended_actions.length - 1} alternative(s)</summary>
                  <ul>
                    {r.recommended_actions.slice(1).map((a) => (
                      <li key={a.rank}>
                        <strong>#{a.rank} {a.action}</strong> — breach {(a.breach_probability_after * 100).toFixed(0)}% / {a.estimated_tonnes_delayed.toFixed(0)}t
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Mine map">
        <MapCard mineState={mineState.data ?? null} windDirectionDeg={null} windSpeed={null} />
      </ErrorBoundary>

      <ErrorBoundary label="Sensor health">
        <Card title="Sensor health">
          {sensorHealth.data
            ? <SensorHealthStrip sensors={sensorHealth.data} />
            : <p className="muted">Loading…</p>}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Event timeline">
        <Card title="Recent dust events">
          {events.initialLoading && <p className="muted">Loading…</p>}
          {events.data && events.data.length === 0 && <p className="muted">No recent events.</p>}
          <ul className="event-list">
            {events.data?.slice(0, 10).map((e) => (
              <li key={e.event_id}>
                <span className="muted">{new Date(e.detected_at).toLocaleTimeString()}</span>
                {' '}{e.breach_occurred ? <strong>BREACH</strong> : <span>elevated</span>}
                {' '}<code>{e.affected_station}</code>
                {' '}<span className="muted">via {e.event_source}</span>
              </li>
            ))}
          </ul>
        </Card>
      </ErrorBoundary>

      {decisionMode && r && (
        <ApproveRejectOverrideModal
          recommendationId={r.recommendation_id}
          primaryAction={primaryAction}
          mode={decisionMode}
          onClose={() => setDecisionMode(null)}
          onDecided={() => recommendation.reload()}
        />
      )}
    </div>
  );
}
