interface Props {
  warnings: string[];
}

export function DataQualityWarning({ warnings }: Props) {
  if (!warnings.length) return null;
  return (
    <div className="warning-row" role="alert">
      {warnings.map((w, i) => (
        <div key={i}>⚠ {w}</div>
      ))}
    </div>
  );
}
