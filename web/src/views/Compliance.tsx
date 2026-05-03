import { useMemo } from 'react';
import { CalibrationBadge } from '../components/CalibrationBadge';
import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { EvidenceChip } from '../components/EvidenceChip';
import { PerReceptorTable } from '../components/PerReceptorTable';
import { useApi } from '../hooks/useApi';
import type { PerReceptorEntry } from '../api/types';
import { api } from '../api/client';
import { complianceKpis } from '../api/kpi';
import { SensorHealthStrip } from './SensorHealthStrip';
import { AuditTrail } from './AuditTrail';

const PM10_THRESHOLD = 50;  // WHO 24h default; site_config will override in K
const PM25_THRESHOLD = 15;

export function Compliance() {
  const forecasts = useApi(() => api.forecastsHistory(), 60_000);
  const sensorHealth = useApi(() => api.sensorHealth(), 60_000);
  const audit = useApi(() => api.audit({ since_minutes: 60 * 24, limit: 200 }), 60_000);
  const events = useApi(() => api.dustEvents(), 60_000);
  const attributions = useApi(() => api.attributions(), 60_000);
  const performance = useApi(
    () => api.modelPerformance().catch(() => null),
    5 * 60_000,
  );

  const kpis = useMemo(
    () => complianceKpis(forecasts.data ?? [], PM10_THRESHOLD),
    [forecasts.data],
  );
  const latestMetric = performance.data?.[0] ?? null;
  const latestProtocol = latestMetric?.metric_payload?.protocol;
  const latestEce = (latestMetric?.metric_payload?.ece as number | null | undefined) ?? null;
  const calibrationOverrideReason =
    (latestProtocol?.warnings ?? []).find((w) =>
      /calibration acceptance gate overridden/.test(w),
    ) ?? null;
  const perReceptor =
    (latestMetric?.metric_payload?.per_receptor as
      | Record<string, PerReceptorEntry>
      | null
      | undefined) ?? null;

  return (
    <div className="view-grid">
      <ErrorBoundary label="PM trends">
        <Card title="PM rolling averages" subtitle={`Last ${kpis.windowSize} predictions · WHO defaults`}>
          <ul className="action-metrics">
            <li>Avg PM10: <strong>{kpis.avgPm10.toFixed(1)}</strong> µg/m³ (limit {PM10_THRESHOLD})</li>
            <li>Avg PM2.5: <strong>{kpis.avgPm25.toFixed(1)}</strong> µg/m³ (limit {PM25_THRESHOLD})</li>
            <li>Forecast breaches: <strong>{kpis.forecastBreaches}</strong></li>
          </ul>
          <p className="muted">Site-specific permit limits override these defaults (see site_config).</p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Sensor health detail">
        <Card title="Sensor health detail">
          {sensorHealth.data
            ? (
              <>
                <SensorHealthStrip sensors={sensorHealth.data} />
                <table className="audit-table">
                  <thead><tr><th>Sensor</th><th>Status</th><th>Quality</th><th>Issues</th></tr></thead>
                  <tbody>
                    {sensorHealth.data.map(s => (
                      <tr key={s.sensor_id}>
                        <td><code>{s.sensor_id}</code></td>
                        <td>{s.status}</td>
                        <td>{s.quality_score.toFixed(2)}</td>
                        <td className="muted">{s.issues.join(', ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : <p className="muted">Loading…</p>}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Event reports">
        <Card title="Dust events">
          {events.data?.length
            ? (
              <ul className="event-list">
                {events.data.slice(0, 20).map(e => (
                  <li key={e.event_id}>
                    <span className="muted">{new Date(e.detected_at).toLocaleString()}</span>
                    {' '}{e.breach_occurred ? <strong>BREACH</strong> : <span>elevated</span>}
                    {' · '}<code>{e.affected_station}</code>
                    {' '}<span className="muted">via {e.event_source}</span>
                  </li>
                ))}
              </ul>
            )
            : <p className="muted">No events recorded.</p>}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Source attributions">
        <Card
          title="Source attributions"
          subtitle="Most recent · evidence class shown for every claim"
        >
          {attributions.data?.length
            ? (
              <ul className="event-list">
                {attributions.data.slice(0, 20).map(a => (
                  <li key={a.attribution_id}>
                    <span className="muted">{new Date(a.issued_at).toLocaleString()}</span>
                    {' · '}<code>{a.affected_station}</code>
                    {' '}<EvidenceChip evidenceClass={a.evidence_class} />
                    <span className="muted"> · {Math.round(a.confidence * 100)}% conf</span>
                    {a.probable_sources[0] && (
                      <div className="reason">
                        Top: <strong>{a.probable_sources[0].source}</strong>
                        {' · '}{a.probable_sources[0].reason}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )
            : <p className="muted">No attributions recorded.</p>}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Model calibration">
        <Card
          title="Model calibration"
          subtitle={
            latestMetric
              ? `Latest: ${latestMetric.model_version} @ ${new Date(latestMetric.evaluated_at).toLocaleString()}`
              : 'No evaluations yet'
          }
        >
          {latestMetric ? (
            <>
              <div className="badge-row">
                <CalibrationBadge
                  ece={latestEce}
                  maxEce={latestProtocol?.max_ece}
                  overrideReason={calibrationOverrideReason}
                />
                <span className="muted">
                  protocol {latestProtocol?.protocol_version ?? '—'}
                </span>
              </div>
              <p className="muted">
                ECE = expected calibration error (10-bin reliability). Lower is
                better. Gate (`max_ece`) is set per protocol; over-the-gate runs
                require an explicit operator override reason and are flagged here.
              </p>
            </>
          ) : (
            <p className="muted">No model_performance rows yet.</p>
          )}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Per-receptor fairness">
        <Card
          title="Per-receptor fairness (M.4.2)"
          subtitle={
            latestMetric
              ? `${latestMetric.model_version} — sorted worst-MAE first`
              : 'No evaluations yet'
          }
        >
          <PerReceptorTable perReceptor={perReceptor} />
          <p className="muted">
            Per-station split of headline metrics. An aggregate-good
            model can still be unfair to a specific receptor; this
            surface is what the Goodhart-canary discipline checks
            against before any automation promotion.
          </p>
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Audit trail">
        <Card title="Audit trail" subtitle="Last 24h, server-side">
          {audit.data ? <AuditTrail entries={audit.data} /> : <p className="muted">Loading…</p>}
        </Card>
      </ErrorBoundary>
    </div>
  );
}
