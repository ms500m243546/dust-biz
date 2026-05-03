import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PerReceptorTable, tierRow } from '../components/PerReceptorTable';
import type { PerReceptorEntry } from '../api/types';

describe('PerReceptorTable', () => {
  it('renders empty state when per_receptor is null', () => {
    render(<PerReceptorTable perReceptor={null} />);
    expect(screen.getByText(/No per-receptor breakdown available/)).toBeInTheDocument();
  });

  it('renders empty state when per_receptor is empty dict', () => {
    render(<PerReceptorTable perReceptor={{}} />);
    expect(screen.getByText(/No per-receptor breakdown available/)).toBeInTheDocument();
  });

  it('renders one row per receptor sorted by worst MAE first', () => {
    const data: Record<string, PerReceptorEntry> = {
      'good-station': { mae_pm10: 5.0, breach_recall: 0.9, sample_count: 100 },
      'bad-station': { mae_pm10: 28.0, breach_recall: 0.4, sample_count: 50 },
      'middling': { mae_pm10: 12.0, breach_recall: 0.7, sample_count: 80 },
    };
    const { container } = render(<PerReceptorTable perReceptor={data} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain('bad-station');
    expect(rows[1].textContent).toContain('middling');
    expect(rows[2].textContent).toContain('good-station');
  });

  it('renders dashes for null metrics', () => {
    const data: Record<string, PerReceptorEntry> = {
      'no-data': {
        mae_pm10: null,
        breach_recall: null,
        breach_precision: null,
        false_positive_rate: null,
      },
    };
    render(<PerReceptorTable perReceptor={data} />);
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});

describe('tierRow', () => {
  it('returns red when MAE is well above threshold', () => {
    expect(tierRow({ mae_pm10: 50 }, 30, 0.5)).toBe('red');
  });
  it('returns red when recall is well below threshold', () => {
    expect(tierRow({ breach_recall: 0.1 }, 30, 0.5)).toBe('red');
  });
  it('returns yellow when MAE just above threshold', () => {
    expect(tierRow({ mae_pm10: 35 }, 30, 0.5)).toBe('yellow');
  });
  it('returns yellow when recall just below threshold', () => {
    expect(tierRow({ breach_recall: 0.4 }, 30, 0.5)).toBe('yellow');
  });
  it('returns grey when both metrics within bounds', () => {
    expect(tierRow({ mae_pm10: 10, breach_recall: 0.8 }, 30, 0.5)).toBe('grey');
  });
  it('returns grey when no metrics provided', () => {
    expect(tierRow({}, 30, 0.5)).toBe('grey');
  });
});
