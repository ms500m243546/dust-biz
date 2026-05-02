import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';
import { SensorHealthStrip } from './SensorHealthStrip';
import { AuditTrail } from './AuditTrail';

const PM10_THRESHOLD = 50;  // WHO 24h default
const PM25_THRESHOLD = 15;

export function Compliance() {
  const forecasts = useApi(() => api.forecastsHistory(), [], 60_000);
  const sensorHealth = useApi(() => api.sensorHealth(), [], 60_000);
  const audit = useApi(() => api.auditFromApprovalsAndOutcomes(), [], 60_000);
  const events = useApi(() => api.dustEvents(), [], 60_000);

  const recent = forecasts.data ?? [];
  const breaches = recent.filter(f => (f.pm10_predicted ?? 0) >= PM10_THRESHOLD).length;
  const avgPm10 = recent.length
    ? recent.reduce((s, f) => s + (f.pm10_predicted ?? 0), 0) / recent.length
    : 0;
  const avgPm25 = recent.length
    ? recent.reduce((s, f) => s + (f.pm25_predicted ?? 0), 0) / recent.length
    : 0;

  return (
    <div className="view-grid">
      <ErrorBoundary label="PM trends">
        <Card
          title="PM rolling averages"
          subtitle={`Last ${recent.length} predictions · WHO defaults shown`}
        >
          <ul className="action-metrics">
            <li>Avg PM10: <strong>{avgPm10.toFixed(1)}</strong> µg/m³ (limit {PM10_THRESHOLD})</li>
            <li>Avg PM2.5: <strong>{avgPm25.toFixed(1)}</strong> µg/m³ (limit {PM25_THRESHOLD})</li>
            <li>Forecast breaches: <strong>{breaches}</strong></li>
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
                  <thead><tr><th>Sensor</th><th>Status</th><th>Quality</th><th>Reasons</th></tr></thead>
                  <tbody>
                    {sensorHealth.data.map(s => (
                      <tr key={s.sensor_id}>
                        <td><code>{s.sensor_id}</code></td>
                        <td>{s.status}</td>
                        <td>{s.data_quality_score.toFixed(2)}</td>
                        <td className="muted">{s.reasons.join(', ') || '—'}</td>
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
                    {' '}<strong>{e.severity}</strong> · <code>{e.zone_id ?? e.sensor_id}</code>
                    {' '}<span className="muted">via {e.event_source}</span>
                  </li>
                ))}
              </ul>
            )
            : <p className="muted">No events recorded.</p>}
        </Card>
      </ErrorBoundary>

      <ErrorBoundary label="Audit trail">
        <Card title="Audit trail" subtitle="Approvals + outcomes">
          {audit.data ? <AuditTrail entries={audit.data} /> : <p className="muted">Loading…</p>}
        </Card>
      </ErrorBoundary>
    </div>
  );
}
