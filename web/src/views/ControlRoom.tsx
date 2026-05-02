import { useState } from 'react';
import { Card } from '../components/Card';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { riskClassToStatus, StatusPill } from '../components/StatusPill';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';
import { MapCard } from './MapCard';
import { SensorHealthStrip } from './SensorHealthStrip';
import { ApproveRejectOverrideModal } from './ApproveRejectOverrideModal';

export function ControlRoom() {
  const forecast = useApi(() => api.forecastsCurrent(), [], 30_000);
  const recommendation = useApi(() => api.recommendationsCurrent(), [], 30_000);
  const attributions = useApi(() => api.attributions(), [], 60_000);
  const mineState = useApi(() => api.mineStateCurrent().catch(() => null), [], 30_000);
  const sensorHealth = useApi(() => api.sensorHealth(), [], 60_000);
  const events = useApi(() => api.dustEvents(), [], 60_000);
  const [decisionMode, setDecisionMode] = useState<null | 'approve' | 'reject' | 'override'>(null);

  const f = forecast.data;
  const r = recommendation.data;

  return (
    <div className="view-grid view-grid-control">
      <ErrorBoundary label="Forecast">
        <Card
          title="Current dust risk"
          subtitle={f ? `${f.target.target_type}:${f.target.target_id} · horizon ${f.horizon_minutes}m` : '—'}
          status={riskClassToStatus(f?.risk_class)}
          warnings={f?.data_quality_warnings ?? []}
        >
          {forecast.loading && <p className="muted">Loading forecast…</p>}
          {forecast.error && <p className="error-row">{forecast.error.message}</p>}
          {f ? (
            <>
              <div className="big-metric">
                <span className="value">{f.pm10_predicted?.toFixed(0) ?? '—'}</span>
                <span className="unit">µg/m³ PM10</span>
              </div>
              <div className="muted">PM2.5 {f.pm25_predicted?.toFixed(0) ?? '—'} · breach prob {(f.breach_probability * 100).toFixed(0)}%</div>
              <ConfidenceBadge confidence={f.confidence} note={`model ${f.model_version}`} />
              <p className="reason">{f.reason}</p>
            </>
          ) : (
            !forecast.loading && <p className="muted">No forecast available yet.</p>
          )}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Likely cause">
        <Card title="Likely cause" subtitle="Top probable sources">
          {attributions.loading && <p className="muted">Loading…</p>}
          {attributions.data && attributions.data.length === 0 && <p className="muted">No attributions yet.</p>}
          {attributions.data?.slice(0, 1).map((a) => (
            <div key={a.attribution_id}>
              <ConfidenceBadge confidence={a.confidence} />
              <ol className="cause-list">
                {a.probable_sources.slice(0, 3).map((src, i) => (
                  <li key={i}>
                    <strong>{src.source_id}</strong>
                    <span className="muted"> · {(src.contribution_estimate * 100).toFixed(0)}% · {Math.round(src.confidence * 100)}% conf</span>
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
          actions={r && (
            <>
              <button
                className="btn-approve"
                onClick={() => setDecisionMode('approve')}
                disabled={r.primary_action.risk_class !== 'low'}
                title={r.primary_action.risk_class !== 'low' ? 'High/medium risk: must override or reject (G1)' : ''}
              >
                Approve
              </button>
              <button className="btn-reject" onClick={() => setDecisionMode('reject')}>Reject</button>
              <button className="btn-override" onClick={() => setDecisionMode('override')}>Override</button>
            </>
          )}
        >
          {recommendation.loading && <p className="muted">Loading…</p>}
          {!r && !recommendation.loading && <p className="muted">No active recommendation.</p>}
          {r && (
            <>
              <div className="action-headline">
                <StatusPill status={riskClassToStatus(r.primary_action.risk_class)} label={r.primary_action.risk_class.toUpperCase()} />
                <strong>{r.primary_action.intervention_id}</strong>
              </div>
              <p>{r.primary_action.description}</p>
              <ul className="action-metrics">
                <li>Dust reduction: <strong>{(r.primary_action.estimated_dust_reduction * 100).toFixed(0)}%</strong></li>
                <li>Tonnes delayed: <strong>{r.primary_action.estimated_tonnes_delayed.toFixed(0)}</strong></li>
                <li>Time to effect: <strong>{r.primary_action.estimated_time_to_effect_minutes}m</strong></li>
              </ul>
              <ConfidenceBadge confidence={r.confidence} note={r.compliance_priority_triggered ? 'compliance priority' : undefined} />
              <p className="reason">{r.reason}</p>
              {r.alternatives.length > 0 && (
                <details>
                  <summary>{r.alternatives.length} alternative(s)</summary>
                  <ul>
                    {r.alternatives.map((a, i) => (
                      <li key={i}>
                        <strong>{a.intervention_id}</strong> — {(a.estimated_dust_reduction * 100).toFixed(0)}% / {a.estimated_tonnes_delayed.toFixed(0)}t
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
        <MapCard
          mineState={mineState.data}
          windDirectionDeg={null}
          windSpeed={null}
        />
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
          {events.loading && <p className="muted">Loading…</p>}
          {events.data && events.data.length === 0 && <p className="muted">No recent events.</p>}
          <ul className="event-list">
            {events.data?.slice(0, 10).map((e) => (
              <li key={e.event_id}>
                <span className="muted">{new Date(e.detected_at).toLocaleTimeString()}</span>
                {' '}<strong>{e.severity}</strong>
                {' '}<code>{e.zone_id ?? e.sensor_id ?? '?'}</code>
                {' '}<span className="muted">via {e.event_source}</span>
              </li>
            ))}
          </ul>
        </Card>
      </ErrorBoundary>

      {decisionMode && r && (
        <ApproveRejectOverrideModal
          recommendationId={r.recommendation_id}
          mode={decisionMode}
          onClose={() => setDecisionMode(null)}
          onDecided={() => recommendation.reload()}
        />
      )}
    </div>
  );
}
