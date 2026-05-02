import type { RiskClass } from '../api/types';

export type CardStatus = 'green' | 'yellow' | 'red' | 'grey';

const LABELS: Record<CardStatus, string> = {
  green: 'NOMINAL',
  yellow: 'ELEVATED',
  red: 'BREACH RISK',
  grey: 'NO DATA',
};

export function StatusPill({ status, label }: { status: CardStatus; label?: string }) {
  return <span className={`status-pill status-${status}`}>{label ?? LABELS[status]}</span>;
}

export function riskClassToStatus(risk: RiskClass | null | undefined): CardStatus {
  if (risk === 'high') return 'red';
  if (risk === 'medium') return 'yellow';
  if (risk === 'low') return 'green';
  return 'grey';
}

export function breachProbabilityToStatus(p: number | undefined | null): CardStatus {
  if (p == null) return 'grey';
  if (p >= 0.85) return 'red';
  if (p >= 0.5) return 'yellow';
  return 'green';
}
