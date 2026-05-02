import type { ReactNode } from 'react';

interface CardProps {
  title: string;
  subtitle?: string;
  status?: 'green' | 'yellow' | 'red' | 'grey';
  children: ReactNode;
  actions?: ReactNode;
  warnings?: string[];
  stale?: boolean;
  staleAge?: string;
}

const STATUS_LABEL: Record<NonNullable<CardProps['status']>, string> = {
  green: 'NOMINAL',
  yellow: 'ELEVATED',
  red: 'BREACH RISK',
  grey: 'NO DATA',
};

export function Card({ title, subtitle, status, children, actions, warnings, stale, staleAge }: CardProps) {
  return (
    <section className={`card${status ? ` card-status-${status}` : ''}`}>
      <header className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <div className="card-sub">{subtitle}</div>}
        </div>
        <div className="card-head-right">
          {status && <span className={`status-pill status-${status}`}>{STATUS_LABEL[status]}</span>}
          {stale && <span className="stale-badge">STALE{staleAge ? ` · ${staleAge}` : ''}</span>}
        </div>
      </header>
      {warnings && warnings.length > 0 && (
        <div className="warning-row">
          {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
      <div className="card-body">{children}</div>
      {actions && <footer className="card-actions">{actions}</footer>}
    </section>
  );
}
