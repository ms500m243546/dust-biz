import type { EvidenceClass } from '../api/types';

interface Props {
  evidenceClass: EvidenceClass;
}

const LABELS: Record<EvidenceClass, string> = {
  experimental: 'EXPERIMENTAL',
  quasi_experimental: 'QUASI-EXPERIMENTAL',
  observational_correlational: 'OBSERVATIONAL',
  expert_judgment: 'EXPERT JUDGMENT',
};

const TIERS: Record<EvidenceClass, 'strong' | 'mid' | 'weak'> = {
  experimental: 'strong',
  quasi_experimental: 'strong',
  observational_correlational: 'weak',
  expert_judgment: 'weak',
};

const TOOLTIPS: Record<EvidenceClass, string> = {
  experimental:
    'RCT-grade evidence. Causal claims are supported by intervention-vs-control comparison.',
  quasi_experimental:
    'Stronger-than-correlational (propensity matching, IV, natural experiment). Causal claims are reasonable.',
  observational_correlational:
    'Single-station historical correlation. Causal claims are NOT supported — predictive only.',
  expert_judgment:
    'RCA / expert-attributed. Evaluation-only; cannot be used as a training label for a causal model.',
};

export function EvidenceChip({ evidenceClass }: Props) {
  const tier = TIERS[evidenceClass];
  return (
    <span
      className={`evidence-chip evidence-${tier}`}
      title={TOOLTIPS[evidenceClass]}
    >
      {LABELS[evidenceClass]}
    </span>
  );
}
