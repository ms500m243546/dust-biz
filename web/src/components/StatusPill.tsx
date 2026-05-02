type Status = 'green' | 'yellow' | 'red' | 'grey';

const LABELS: Record<Status, string> = {
  green: 'NOMINAL',
  yellow: 'ELEVATED',
  red: 'BREACH RISK',
  grey: 'NO DATA',
};

export function StatusPill({ status, label }: { status: Status; label?: string }) {
  return <span className={`status-pill status-${status}`}>{label ?? LABELS[status]}</span>;
}

export function riskClassToStatus(risk: 'low' | 'medium' | 'high' | undefined | null): Status {
  if (risk === 'high') return 'red';
  if (risk === 'medium') return 'yellow';
  if (risk === 'low') return 'green';
  return 'grey';
}
