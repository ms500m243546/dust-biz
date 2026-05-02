import type { SensorHealthSchema } from '../api/types';

const STATUS_COLOR: Record<string, string> = {
  ok: '#3d9a55',
  degraded: '#d7a02b',
  offline: '#a0a0a0',
  stale: '#a0a0a0',
};

export function SensorHealthStrip({ sensors }: { sensors: SensorHealthSchema[] }) {
  if (!sensors.length) return <p className="muted">No sensors reporting.</p>;
  const ok = sensors.filter(s => s.status === 'ok').length;
  return (
    <div>
      <div className="muted">{ok} / {sensors.length} sensors healthy</div>
      <div className="sensor-strip">
        {sensors.map((s) => (
          <span
            key={s.sensor_id}
            className="sensor-tile"
            title={`${s.sensor_id} · ${s.status} · q=${s.data_quality_score.toFixed(2)}`}
            style={{ background: STATUS_COLOR[s.status] ?? '#888' }}
          />
        ))}
      </div>
    </div>
  );
}
