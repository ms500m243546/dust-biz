import type { PerReceptorEntry } from '../api/types';

interface Props {
  perReceptor: Record<string, PerReceptorEntry> | null | undefined;
  // Highlight thresholds — receptor metrics worse than these get a
  // visual flag. Defaults match the conservative mine deployment
  // posture (PM10 MAE 30 µg/m³, recall 50%).
  maeThreshold?: number;
  recallThreshold?: number;
}

const DEFAULT_MAE_THRESHOLD = 30.0;
const DEFAULT_RECALL_THRESHOLD = 0.5;

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return '—';
  return v.toFixed(digits);
}

// Tier each row by whichever metric it most clearly fails. Used for
// the per-row left-border tint so an operator scanning the table
// sees the worst-receptor offender at a glance.
export function tierRow(
  entry: PerReceptorEntry,
  maeThreshold: number,
  recallThreshold: number,
): 'red' | 'yellow' | 'grey' {
  const mae = entry.mae_pm10 ?? null;
  const recall = entry.breach_recall ?? null;
  if (mae !== null && mae > maeThreshold * 1.5) return 'red';
  if (recall !== null && recall < recallThreshold * 0.5) return 'red';
  if (mae !== null && mae > maeThreshold) return 'yellow';
  if (recall !== null && recall < recallThreshold) return 'yellow';
  return 'grey';
}

export function PerReceptorTable({
  perReceptor,
  maeThreshold = DEFAULT_MAE_THRESHOLD,
  recallThreshold = DEFAULT_RECALL_THRESHOLD,
}: Props) {
  const rows = perReceptor ? Object.entries(perReceptor) : [];
  if (rows.length === 0) {
    return (
      <p className="muted">
        No per-receptor breakdown available — single-receptor evaluation
        or empty observed window.
      </p>
    );
  }
  const sorted = rows.sort(([, a], [, b]) => {
    const am = a.mae_pm10 ?? -Infinity;
    const bm = b.mae_pm10 ?? -Infinity;
    return bm - am;
  });
  return (
    <table className="audit-table per-receptor-table">
      <thead>
        <tr>
          <th>Receptor</th>
          <th>Samples</th>
          <th>MAE PM10</th>
          <th>Recall</th>
          <th>Precision</th>
          <th>FPR</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(([sid, entry]) => {
          const tier = tierRow(entry, maeThreshold, recallThreshold);
          return (
            <tr key={sid} className={`per-receptor-row per-receptor-${tier}`}>
              <td><code>{sid}</code></td>
              <td>{entry.sample_count ?? '—'}</td>
              <td>{fmt(entry.mae_pm10)}</td>
              <td>{fmt(entry.breach_recall, 3)}</td>
              <td>{fmt(entry.breach_precision, 3)}</td>
              <td>{fmt(entry.false_positive_rate, 3)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
