import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { StatusPill, riskClassToStatus, breachProbabilityToStatus } from '../components/StatusPill';
import { DataQualityWarning } from '../components/DataQualityWarning';
import { Card } from '../components/Card';

describe('shared components', () => {
  it('ConfidenceBadge renders percentage and tier', () => {
    render(<ConfidenceBadge confidence={0.82} note="model v1" />);
    expect(screen.getByText('82%')).toBeInTheDocument();
    expect(screen.getByText('confidence')).toBeInTheDocument();
  });

  it('riskClassToStatus maps risk classes', () => {
    expect(riskClassToStatus('high')).toBe('red');
    expect(riskClassToStatus('medium')).toBe('yellow');
    expect(riskClassToStatus('low')).toBe('green');
    expect(riskClassToStatus(null)).toBe('grey');
  });

  it('breachProbabilityToStatus maps thresholds', () => {
    expect(breachProbabilityToStatus(null)).toBe('grey');
    expect(breachProbabilityToStatus(0.1)).toBe('green');
    expect(breachProbabilityToStatus(0.6)).toBe('yellow');
    expect(breachProbabilityToStatus(0.9)).toBe('red');
  });

  it('StatusPill renders label', () => {
    render(<StatusPill status="red" />);
    expect(screen.getByText('BREACH RISK')).toBeInTheDocument();
  });

  it('DataQualityWarning hides when empty', () => {
    const { container } = render(<DataQualityWarning warnings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('DataQualityWarning shows warnings', () => {
    render(<DataQualityWarning warnings={['sensor S1 stale']} />);
    expect(screen.getByText(/sensor S1 stale/)).toBeInTheDocument();
  });

  it('Card renders title, status pill, and warnings', () => {
    render(
      <Card title="Test" status="yellow" warnings={['hot']}>
        <p>body</p>
      </Card>,
    );
    expect(screen.getByText('Test')).toBeInTheDocument();
    expect(screen.getByText('ELEVATED')).toBeInTheDocument();
    expect(screen.getByText(/hot/)).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });
});
