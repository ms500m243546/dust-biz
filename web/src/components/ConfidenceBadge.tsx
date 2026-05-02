interface Props {
  confidence: number;
  note?: string;
}

export function ConfidenceBadge({ confidence, note }: Props) {
  const pct = Math.round(confidence * 100);
  const tier = pct >= 75 ? 'high' : pct >= 50 ? 'mid' : 'low';
  return (
    <div className={`confidence confidence-${tier}`} title={note}>
      <span className="confidence-pct">{pct}%</span>
      <span className="confidence-label">confidence</span>
      {note && <span className="confidence-note">{note}</span>}
    </div>
  );
}
