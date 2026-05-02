import type { ReactNode } from 'react';
import { StatusPill, type CardStatus } from './StatusPill';

interface CardProps {
  title: string;
  subtitle?: string;
  status?: CardStatus;
  children: ReactNode;
  actions?: ReactNode;
  warnings?: string[];
  stale?: boolean;
  staleAge?: string;
}

export function Card({ title, subtitle, status, children, actions, warnings, stale, staleAge }: CardProps) {
  return (
    <section className={`card${status ? ` card-status-${status}` : ''}`}>
      <header className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <div className="card-sub">{subtitle}</div>}
        </div>
        <div className="card-head-right">
          {status && <StatusPill status={status} />}
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
