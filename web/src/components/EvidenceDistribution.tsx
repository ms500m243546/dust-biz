import type { EvidenceClass, SourceAttributionSchema } from '../api/types';

interface Props {
  attributions: SourceAttributionSchema[] | null | undefined;
}

const ORDER: EvidenceClass[] = [
  'experimental',
  'quasi_experimental',
  'observational_correlational',
  'expert_judgment',
];

const LABEL: Record<EvidenceClass, string> = {
  experimental: 'EXPERIMENTAL',
  quasi_experimental: 'QUASI-EXP.',
  observational_correlational: 'OBSERVATIONAL',
  expert_judgment: 'EXPERT JUDG.',
};

const TIER_CLASS: Record<EvidenceClass, string> = {
  experimental: 'evidence-strong',
  quasi_experimental: 'evidence-strong',
  observational_correlational: 'evidence-weak',
  expert_judgment: 'evidence-weak',
};

// Phase T.3 — aggregate distribution of EvidenceClass across the
// most recent attributions. Mini horizontal-stacked bar so an
// operator can see at a glance how many attributions are
// quasi-experimental (strong) vs expert-judgment (weak).
export function evidenceDistribution(
  attributions: SourceAttributionSchema[] | null | undefined,
): Record<EvidenceClass, number> {
  const out: Record<EvidenceClass, number> = {
    experimental: 0,
    quasi_experimental: 0,
    observational_correlational: 0,
    expert_judgment: 0,
  };
  if (!attributions) return out;
  for (const a of attributions) {
    out[a.evidence_class] = (out[a.evidence_class] ?? 0) + 1;
  }
  return out;
}

export function EvidenceDistribution({ attributions }: Props) {
  const counts = evidenceDistribution(attributions);
  const total = ORDER.reduce((s, k) => s + counts[k], 0);
  if (total === 0) {
    return <p className="muted">No attributions yet.</p>;
  }
  return (
    <div className="evidence-dist">
      <div className="evidence-bar" data-testid="evidence-bar">
        {ORDER.map((k) => {
          const n = counts[k];
          if (n === 0) return null;
          const widthPct = (n / total) * 100;
          return (
            <span
              key={k}
              className={`evidence-bar-segment ${TIER_CLASS[k]}`}
              style={{ width: `${widthPct}%` }}
              title={`${LABEL[k]}: ${n}/${total} (${widthPct.toFixed(0)}%)`}
            />
          );
        })}
      </div>
      <ul className="evidence-legend">
        {ORDER.map((k) => (
          <li key={k} className="evidence-legend-row">
            <span className={`evidence-chip ${TIER_CLASS[k]}`}>{LABEL[k]}</span>
            <span className="muted">{counts[k]} of {total}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
