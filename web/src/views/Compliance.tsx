import { useMemo } from 'react';
import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useApi } from '../hooks/useApi';
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

  const kpis = useMemo(
    () => complianceKpis(forecasts.data ?? [], PM10_THRESHOLD),
    [forecasts.data],
  );

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

      <ErrorBoundary label="Audit trail">
        <Card title="Audit trail" subtitle="Last 24h, server-side">
          {audit.data ? <AuditTrail entries={audit.data} /> : <p className="muted">Loading…</p>}
        </Card>
      </ErrorBoundary>
    </div>
  );
}
