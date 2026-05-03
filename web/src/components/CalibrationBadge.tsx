interface Props {
  ece: number | null | undefined;
  maxEce: number | undefined;
  overrideReason?: string | null;
}

// Maps ECE relative to the gate threshold to a tier. "good" means well
// inside the gate (ECE <= 50% of max); "marginal" means inside the gate
// but >50%; "over" means above the gate (only possible when an override
// was applied).
function tier(
  ece: number | null | undefined,
  maxEce: number | undefined,
): 'good' | 'marginal' | 'over' | 'unknown' {
  if (ece == null || maxEce == null) return 'unknown';
  if (ece > maxEce) return 'over';
  if (ece > maxEce * 0.5) return 'marginal';
  return 'good';
}

export function CalibrationBadge({ ece, maxEce, overrideReason }: Props) {
  const t = tier(ece, maxEce);
  const eceText = ece == null ? 'n/a' : ece.toFixed(3);
  const gateText = maxEce == null ? 'n/a' : maxEce.toFixed(3);
  const title =
    t === 'over' && overrideReason
      ? `ECE=${eceText} > gate ${gateText}; override: ${overrideReason}`
      : `ECE=${eceText} (gate ${gateText}). Lower is better.`;
  const label =
    t === 'over'
      ? 'CAL OVERRIDE'
      : t === 'marginal'
      ? 'CAL MARGINAL'
      : t === 'good'
      ? 'CAL OK'
      : 'CAL UNKNOWN';
  return (
    <span className={`calibration-badge calibration-${t}`} title={title}>
      {label}
      <span className="calibration-ece">{eceText}</span>
    </span>
  );
}
