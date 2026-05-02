import type { SensorHealthStatusSchema, SensorStatus } from '../api/types';

const STATUS_COLOR: Record<SensorStatus, string> = {
  healthy: '#3d9a55',
  degraded: '#d7a02b',
  offline: '#a0a0a0',
  unknown: '#a0a0a0',
};

export function SensorHealthStrip({ sensors }: { sensors: SensorHealthStatusSchema[] }) {
  if (!sensors.length) return <p className="muted">No sensors reporting.</p>;
  const healthy = sensors.filter(s => s.status === 'healthy').length;
  return (
    <div>
      <div className="muted">{healthy} / {sensors.length} sensors healthy</div>
      <div className="sensor-strip">
        {sensors.map((s) => (
          <span
            key={s.sensor_id}
            className="sensor-tile"
            title={`${s.sensor_id} · ${s.status} · q=${s.quality_score.toFixed(2)}`}
            style={{ background: STATUS_COLOR[s.status] }}
          />
        ))}
      </div>
    </div>
  );
}
