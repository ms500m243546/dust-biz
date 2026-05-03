import { describe, expect, it, vi, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Drift, distinctModelVersions, driftSeverity } from '../views/Drift';
import { api } from '../api/client';
import type { DriftAlertSchema, ModelPerformanceMetricSchema } from '../api/types';

function metricRow(version: string, evaluatedAt: string): ModelPerformanceMetricSchema {
  return {
    metric_id: 1,
    model_version: version,
    model_kind: 'dust_forecast',
    evaluated_at: evaluatedAt,
    window_from: '2026-01-01T00:00:00Z',
    window_to: '2026-01-02T00:00:00Z',
    sample_count: 24,
    metric_payload: {},
  };
}

function alert(over: Partial<DriftAlertSchema>): DriftAlertSchema {
  return {
    model_version: 'dust_forecast_v0.1.0',
    metric_name: 'breach_recall',
    baseline_value: 0.7,
    recent_value: 0.55,
    delta: 0.15,
    threshold: 0.10,
    baseline_sample_count: 6,
    recent_sample_count: 6,
    detected_at: '2026-05-03T12:00:00Z',
    ...over,
  };
}

describe('drift helpers', () => {
  it('driftSeverity yellow at 1x, red at 2x', () => {
    expect(driftSeverity(0.10, 0.10)).toBe('yellow');
    expect(driftSeverity(0.15, 0.10)).toBe('yellow');
    expect(driftSeverity(0.20, 0.10)).toBe('red');
    expect(driftSeverity(0.50, 0.10)).toBe('red');
  });

  it('distinctModelVersions preserves first-seen order', () => {
    const rows = [
      metricRow('v2', '2026-05-03T00:00:00Z'),
      metricRow('v1', '2026-05-02T00:00:00Z'),
      metricRow('v2', '2026-05-01T00:00:00Z'),
    ];
    expect(distinctModelVersions(rows)).toEqual(['v2', 'v1']);
  });

  it('distinctModelVersions handles null', () => {
    expect(distinctModelVersions(null)).toEqual([]);
  });
});

describe('Drift view', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows empty state when no model_performance rows exist', async () => {
    vi.spyOn(api, 'modelPerformance').mockResolvedValue([]);
    const driftSpy = vi.spyOn(api, 'driftAlerts').mockResolvedValue([]);
    render(<Drift />);
    await waitFor(() => {
      expect(screen.getByText(/No model_performance rows yet/)).toBeInTheDocument();
    });
    // Cannot call drift without a model_version.
    expect(driftSpy).not.toHaveBeenCalled();
  });

  it('renders alerts table when drift is detected', async () => {
    vi.spyOn(api, 'modelPerformance').mockResolvedValue([
      metricRow('dust_forecast_v0.1.0', '2026-05-03T00:00:00Z'),
    ]);
    vi.spyOn(api, 'driftAlerts').mockResolvedValue([
      alert({ metric_name: 'breach_recall', delta: 0.15, threshold: 0.10 }),
      alert({ metric_name: 'ece', delta: 0.06, threshold: 0.025 }),
    ]);
    render(<Drift />);
    await waitFor(() => {
      expect(screen.getByText('breach_recall')).toBeInTheDocument();
    });
    expect(screen.getByText('ece')).toBeInTheDocument();
    // breach_recall: 0.15 / 0.10 = 1.5x → yellow → NOTICE
    // ece: 0.06 / 0.025 = 2.4x → red → ACT
    expect(screen.getByText('ACT')).toBeInTheDocument();
    expect(screen.getByText('NOTICE')).toBeInTheDocument();
  });

  it('renders no-drift empty state when alerts list is empty', async () => {
    vi.spyOn(api, 'modelPerformance').mockResolvedValue([
      metricRow('dust_forecast_v0.1.0', '2026-05-03T00:00:00Z'),
    ]);
    vi.spyOn(api, 'driftAlerts').mockResolvedValue([]);
    render(<Drift />);
    await waitFor(() => {
      expect(screen.getByText(/No drift detected in window/)).toBeInTheDocument();
    });
  });

  it('switching window triggers a refetch with the new since_days', async () => {
    vi.spyOn(api, 'modelPerformance').mockResolvedValue([
      metricRow('dust_forecast_v0.1.0', '2026-05-03T00:00:00Z'),
    ]);
    const driftSpy = vi.spyOn(api, 'driftAlerts').mockResolvedValue([]);
    render(<Drift />);
    await waitFor(() => {
      expect(driftSpy).toHaveBeenCalledWith(
        expect.objectContaining({ since_days: 30, model_version: 'dust_forecast_v0.1.0' }),
      );
    });
    fireEvent.change(screen.getByLabelText('Window in days'), { target: { value: '90' } });
    await waitFor(() => {
      expect(driftSpy).toHaveBeenCalledWith(
        expect.objectContaining({ since_days: 90 }),
      );
    });
  });

  it('renders error row when drift fetch fails', async () => {
    vi.spyOn(api, 'modelPerformance').mockResolvedValue([
      metricRow('dust_forecast_v0.1.0', '2026-05-03T00:00:00Z'),
    ]);
    vi.spyOn(api, 'driftAlerts').mockRejectedValue(new Error('drift offline'));
    render(<Drift />);
    await waitFor(() => {
      expect(screen.getByText(/drift offline/)).toBeInTheDocument();
    });
  });
});
