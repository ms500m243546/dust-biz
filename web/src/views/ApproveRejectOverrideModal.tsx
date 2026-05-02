import { useState } from 'react';
import { api, ApiError } from '../api/client';

interface Props {
  recommendationId: string;
  mode: 'approve' | 'reject' | 'override';
  onClose: () => void;
  onDecided: () => void;
}

export function ApproveRejectOverrideModal({ recommendationId, mode, onClose, onDecided }: Props) {
  const [reason, setReason] = useState('');
  const [overrideAction, setOverrideAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === 'approve') {
        await api.approve(recommendationId);
      } else if (mode === 'reject') {
        if (!reason.trim()) { setError('Reason required'); setBusy(false); return; }
        await api.reject(recommendationId, reason.trim());
      } else {
        if (!overrideAction.trim() || !reason.trim()) {
          setError('Override action and reason both required');
          setBusy(false);
          return;
        }
        await api.override(recommendationId, overrideAction.trim(), reason.trim());
      }
      onDecided();
      onClose();
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.status}: ${(e.body as { detail?: string } | undefined)?.detail ?? e.message}` : String(e);
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const title =
    mode === 'approve' ? 'Approve recommendation' :
    mode === 'reject' ? 'Reject recommendation' : 'Override recommendation';

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p className="muted">Recommendation: <code>{recommendationId}</code></p>
        {mode === 'override' && (
          <label>
            Override action
            <input value={overrideAction} onChange={(e) => setOverrideAction(e.target.value)} placeholder="e.g. water_road_now" />
          </label>
        )}
        {(mode === 'reject' || mode === 'override') && (
          <label>
            Reason (required)
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
          </label>
        )}
        {error && <div className="error-row">{error}</div>}
        <div className="modal-actions">
          <button onClick={onClose} disabled={busy} className="btn-secondary">Cancel</button>
          <button onClick={submit} disabled={busy} className={`btn-${mode}`}>
            {busy ? 'Submitting...' : title}
          </button>
        </div>
      </div>
    </div>
  );
}
