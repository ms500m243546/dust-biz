import type { CrossMineEvalBlock } from '../api/types';

interface Props {
  survivorCaveat: string | null | undefined;
  selectionCaveat: string | null | undefined;
  crossMineEval: CrossMineEvalBlock | null | undefined;
}

// Phase T.2 — surfaces Q.3 multi-station-discipline caveats from the
// latest metric_payload row. Renders nothing when all three fields
// are null (the bias does not apply to the current evaluation).
export function MultiStationCaveats({
  survivorCaveat,
  selectionCaveat,
  crossMineEval,
}: Props) {
  const hasAnything =
    Boolean(survivorCaveat) || Boolean(selectionCaveat) || Boolean(crossMineEval);
  if (!hasAnything) return null;
  return (
    <div className="caveat-stack">
      {survivorCaveat && (
        <div className="warning-row" data-testid="caveat-survivor">
          <strong>Survivorship (B-5):</strong> {survivorCaveat}
        </div>
      )}
      {selectionCaveat && (
        <div className="warning-row" data-testid="caveat-selection">
          <strong>Selection (B-6):</strong> {selectionCaveat}
        </div>
      )}
      {crossMineEval && (
        <div className="warning-row" data-testid="caveat-cross-mine">
          <strong>Distribution shift (B-14):</strong> {crossMineEval.warning}
          <div className="muted" style={{ marginTop: 4 }}>
            Trained on <code>{crossMineEval.trained_on_mine}</code>; evaluated on{' '}
            {crossMineEval.evaluated_on_mines.map((m) => (
              <code key={m} style={{ marginRight: 4 }}>{m}</code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
