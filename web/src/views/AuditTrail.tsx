import type { AuditLogEntry } from '../api/types';

export function AuditTrail({ entries }: { entries: AuditLogEntry[] }) {
  if (!entries.length) return <p className="muted">No audit entries yet.</p>;
  return (
    <table className="audit-table">
      <thead>
        <tr>
          <th>When</th>
          <th>Actor</th>
          <th>Action</th>
          <th>Entity</th>
        </tr>
      </thead>
      <tbody>
        {entries.slice(0, 50).map((e) => (
          <tr key={e.audit_id}>
            <td>{new Date(e.created_at).toLocaleString()}</td>
            <td>{e.actor}</td>
            <td><span className={`audit-action audit-${e.action}`}>{e.action}</span></td>
            <td><code>{e.entity_type}:{e.entity_id}</code></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
