import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card } from '../components/Card';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useApi } from '../hooks/useApi';
import { api } from '../api/client';
import type { DriftAlertSchema } from '../api/types';

const SINCE_OPTIONS = [14, 30, 90] as const;
type SinceDays = (typeof SINCE_OPTIONS)[number];

// Tier a drift alert by severity. ratio = delta / threshold; the
// threshold itself is "noticed" (yellow); 2x is "act now" (red).
export function driftSeverity(delta: number, threshold: number): 'yellow' | 'red' {
  return delta >= threshold * 2 ? 'red' : 'yellow';
}

export function distinctModelVersions(
  rows: { model_version: string }[] | null,
): string[] {
  if (!rows) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rows) {
    if (!seen.has(r.model_version)) {
      seen.add(r.model_version);
      out.push(r.model_version);
    }
  }
  return out;
}

export function Drift() {
  const performance = useApi(() => api.modelPerformance(), 5 * 60_000);
  const versions = useMemo(() => distinctModelVersions(performance.data), [performance.data]);

  const [modelVersion, setModelVersion] = useState<string | null>(null);
  const [sinceDays, setSinceDays] = useState<SinceDays>(30);

  // Default selection follows the most-recent model_version once the
  // performance feed loads. The user can switch via the <select>.
  useEffect(() => {
    if (modelVersion == null && versions.length > 0) {
      setModelVersion(versions[0]);
    }
  }, [versions, modelVersion]);

  const fetchDrift = useCallback(() => {
    if (!modelVersion) return Promise.resolve<DriftAlertSchema[]>([]);
    return api.driftAlerts({ model_version: modelVersion, since_days: sinceDays, min_samples: 4 });
  }, [modelVersion, sinceDays]);

  const drift = useApi(fetchDrift, 60_000);
  // useApi binds its reload on mount only — so when modelVersion or
  // sinceDays change, force a refetch with the new params instead of
  // waiting for the next 60s poll. fnRef inside useApi already points
  // at the latest fetchDrift closure.
  useEffect(() => {
    drift.reload();
    // drift.reload identity is stable; intentionally only react to
    // param changes here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelVersion, sinceDays]);
  const alerts = drift.data ?? [];
  const worstSeverity: 'green' | 'yellow' | 'red' = alerts.length === 0
    ? 'green'
    : alerts.some((a) => driftSeverity(a.delta, a.threshold) === 'red')
    ? 'red'
    : 'yellow';

  return (
    <div className="view-grid">
      <ErrorBoundary label="Drift watch">
        <Card
          title="Model drift watch"
          subtitle="M.4.3 — metric drift between baseline and recent halves of the window"
          status={worstSeverity}
        >
          <div className="badge-row">
            <label>
              <span className="muted">Model&nbsp;</span>
              <select
                value={modelVersion ?? ''}
                onChange={(e) => setModelVersion(e.target.value || null)}
                disabled={versions.length === 0}
                aria-label="Model version"
              >
                {versions.length === 0 && <option value="">no evaluations yet</option>}
                {versions.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              <span className="muted">Window&nbsp;</span>
              <select
                value={sinceDays}
                onChange={(e) => setSinceDays(Number(e.target.value) as SinceDays)}
                aria-label="Window in days"
              >
                {SINCE_OPTIONS.map((d) => (
                  <option key={d} value={d}>{d} days</option>
                ))}
              </select>
            </label>
            {drift.refreshing && <span className="muted">refreshing…</span>}
          </div>

          {drift.error ? (
            <div className="error-row">{drift.error.message}</div>
          ) : !modelVersion ? (
            <p className="muted">No model_performance rows yet — drift cannot be computed.</p>
          ) : drift.initialLoading ? (
            <p className="muted">Loading…</p>
          ) : alerts.length === 0 ? (
            <p className="muted">No drift detected in window.</p>
          ) : (
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Recent</th>
                  <th>|Δ|</th>
                  <th>Threshold</th>
                  <th>Samples (B / R)</th>
                  <th>Detected</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => {
                  const sev = driftSeverity(a.delta, a.threshold);
                  return (
                    <tr key={a.metric_name}>
                      <td>
                        <code>{a.metric_name}</code>
                        <span className={`status-pill status-${sev}`} style={{ marginLeft: 6 }}>
                          {sev === 'red' ? 'ACT' : 'NOTICE'}
                        </span>
                      </td>
                      <td>{formatMetric(a.baseline_value)}</td>
                      <td>{formatMetric(a.recent_value)}</td>
                      <td><strong>{formatMetric(a.delta)}</strong></td>
                      <td className="muted">{formatMetric(a.threshold)}</td>
                      <td className="muted">{a.baseline_sample_count} / {a.recent_sample_count}</td>
                      <td className="muted">{new Date(a.detected_at).toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <p className="muted">
            Detection-only. Operator response (retraining, rollback, override-with-reason)
            is part of the post-M operational playbook. Threshold colour: yellow ≥ 1×
            threshold, red ≥ 2×.
          </p>
        </Card>
      </ErrorBoundary>
    </div>
  );
}

// Probability metrics live in [0, 1]; formatting them as fixed-3 keeps
// the table readable without rounding mae_pm10 (µg/m³) into uselessness.
function formatMetric(value: number): string {
  if (Math.abs(value) >= 1) return value.toFixed(2);
  return value.toFixed(3);
}
