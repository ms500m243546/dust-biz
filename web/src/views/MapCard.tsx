import { useMemo } from 'react';
import { Card } from '../components/Card';
import type { MineStateSchema, WindExposure } from '../api/types';

interface Props {
  mineState: MineStateSchema | null;
  windDirectionDeg?: number | null;
  windSpeed?: number | null;
}

const EXPOSURE_COLOR: Record<WindExposure, string> = {
  high: '#d04444',
  medium: '#d7a02b',
  low: '#3d9a55',
  unknown: '#a0a0a0',
};

export function MapCard({ mineState, windDirectionDeg, windSpeed }: Props) {
  const layout = useMemo(() => {
    if (!mineState) return [];
    const cols = Math.max(1, Math.ceil(Math.sqrt(mineState.zones.length || 1)));
    return mineState.zones.map((zone, i) => ({
      zone,
      x: (i % cols) * 90 + 30,
      y: Math.floor(i / cols) * 90 + 30,
      color: EXPOSURE_COLOR[zone.wind_exposure],
    }));
  }, [mineState]);

  if (!mineState) {
    return (
      <Card title="Mine map" status="grey">
        <p className="muted">Mine state unavailable.</p>
      </Card>
    );
  }

  const anyZoneStale = mineState.zones.some((z) => z.staleness_flags.length > 0);
  const arrowAngle = (windDirectionDeg ?? 0) + 180; // wind FROM → arrow points TO
  return (
    <Card
      title="Mine map"
      subtitle={`${mineState.zones.length} zones · wind ${windSpeed ?? '?'} m/s @ ${windDirectionDeg ?? '?'}°`}
      stale={anyZoneStale}
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
