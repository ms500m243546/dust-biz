interface Props {
  asOf: string | null;
  expectedFreshnessSeconds: number;
}

export function StaleBadge({ asOf, expectedFreshnessSeconds }: Props) {
  if (!asOf) return <span className="stale-badge">NO DATA</span>;
  const age = (Date.now() - new Date(asOf).getTime()) / 1000;
  if (age <= expectedFreshnessSeconds) return null;
  const human = age < 60 ? `${Math.round(age)}s` : age < 3600 ? `${Math.round(age / 60)}m` : `${Math.round(age / 3600)}h`;
  return <span className="stale-badge">STALE · {human}</span>;
}
