import { useMemo } from 'react';
import { Card } from '../components/Card';
import type { MineStateSchema } from '../api/types';

interface Props {
  mineState: MineStateSchema | null;
  windDirectionDeg?: number | null;
  windSpeed?: number | null;
}

const RISK_COLOR: Record<string, string> = {
  high: '#d04444',
  moderate: '#d7a02b',
  low: '#3d9a55',
};

export function MapCard({ mineState, windDirectionDeg, windSpeed }: Props) {
  const layout = useMemo(() => {
    if (!mineState) return [];
    return mineState.zones.map((z, i) => {
      const cols = Math.ceil(Math.sqrt(mineState.zones.length || 1));
      const x = (i % cols) * 90 + 30;
      const y = Math.floor(i / cols) * 90 + 30;
      const exposure = z.wind_exposure;
      return { zone: z, x, y, color: RISK_COLOR[exposure] ?? '#888' };
    });
  }, [mineState]);

  if (!mineState) {
    return (
      <Card title="Mine map" status="grey">
        <p className="muted">Mine state unavailable.</p>
      </Card>
    );
  }

  const arrowAngle = (windDirectionDeg ?? 0) + 180; // wind FROM → arrow points TO
  return (
    <Card
      title="Mine map"
      subtitle={`${mineState.zones.length} zones · wind ${windSpeed ?? '?'} m/s @ ${windDirectionDeg ?? '?'}°`}
      stale={mineState.staleness_flags.length > 0}
    >
      <svg width="100%" viewBox="0 0 600 400" className="mine-map">
        <rect x={0} y={0} width={600} height={400} fill="#f6f3ee" />
        {layout.map(({ zone, x, y, color }) => (
          <g key={zone.zone_id}>
            <circle cx={x} cy={y} r={26} fill={color} opacity={0.75} />
            <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill="#fff">
              {zone.zone_id.slice(0, 8)}
            </text>
            {zone.equipment_active.length > 0 && (
              <text x={x} y={y + 42} textAnchor="middle" fontSize={9} fill="#444">
                {zone.equipment_active.length} eq
              </text>
            )}
          </g>
        ))}
        <g transform={`translate(540, 40) rotate(${arrowAngle})`}>
          <line x1={0} y1={-20} x2={0} y2={20} stroke="#0a0a0a" strokeWidth={2} />
          <polygon points="-5,15 5,15 0,25" fill="#0a0a0a" />
        </g>
        <text x={540} y={75} textAnchor="middle" fontSize={10} fill="#444">wind</text>
      </svg>
    </Card>
  );
}
