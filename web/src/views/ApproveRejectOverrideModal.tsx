import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { RecommendationActionSchema } from '../api/types';

interface Props {
  recommendationId: string;
  primaryAction: RecommendationActionSchema | null;
  mode: 'approve' | 'reject' | 'override';
  onClose: () => void;
  onDecided: () => void;
}

export function ApproveRejectOverrideModal({ recommendationId, primaryAction, mode, onClose, onDecided }: Props) {
  const [humanReason, setHumanReason] = useState('');
  const [overrideAction, setOverrideAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function validate(): string | null {
    if (mode === 'approve') {
      if (!primaryAction) return 'No primary action available to approve';
      return null;
    }
    if (!humanReason.trim()) return 'Reason is required';
    if (mode === 'override' && !overrideAction.trim()) return 'Override action is required';
    return null;
  }

  async function submit() {
    const v = validate();
    if (v) { setError(v); return; }
    setBusy(true);
    setError(null);
    try {
      if (mode === 'approve') {
        await api.approve(recommendationId, {
          chosen_action_rank: primaryAction!.rank,
          human_reason: humanReason.trim() || undefined,
        });
      } else if (mode === 'reject') {
        await api.reject(recommendationId, humanReason.trim());
      } else {
        await api.override(recommendationId, overrideAction.trim(), humanReason.trim());
      }
      onDecided();
      onClose();
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${(e.body as { detail?: string } | undefined)?.detail ?? e.message}`
        : String(e);
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
        {mode === 'approve' && primaryAction && (
          <p className="muted">Approving rank #{primaryAction.rank}: <strong>{primaryAction.action}</strong></p>
        )}
        {mode === 'override' && (
          <label>
            Override action (free text)
            <input value={overrideAction} onChange={(e) => setOverrideAction(e.target.value)} placeholder="e.g. water_road_now" />
          </label>
        )}
        <label>
          Reason {mode === 'approve' ? '(optional)' : '(required)'}
          <textarea value={humanReason} onChange={(e) => setHumanReason(e.target.value)} rows={3} />
        </label>
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
