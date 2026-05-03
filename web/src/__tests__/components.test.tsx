import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CalibrationBadge } from '../components/CalibrationBadge';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { EvidenceChip } from '../components/EvidenceChip';
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

  it('EvidenceChip labels strong and weak tiers', () => {
    const { rerender, container } = render(
      <EvidenceChip evidenceClass="quasi_experimental" />,
    );
    expect(screen.getByText('QUASI-EXPERIMENTAL')).toBeInTheDocument();
    expect(container.querySelector('.evidence-strong')).not.toBeNull();
    rerender(<EvidenceChip evidenceClass="observational_correlational" />);
    expect(screen.getByText('OBSERVATIONAL')).toBeInTheDocument();
    expect(container.querySelector('.evidence-weak')).not.toBeNull();
  });

  it('CalibrationBadge tiers good / marginal / over from ECE vs gate', () => {
    const { rerender, container } = render(
      <CalibrationBadge ece={0.01} maxEce={0.05} />,
    );
    expect(container.querySelector('.calibration-good')).not.toBeNull();
    rerender(<CalibrationBadge ece={0.04} maxEce={0.05} />);
    expect(container.querySelector('.calibration-marginal')).not.toBeNull();
    rerender(
      <CalibrationBadge
        ece={0.2}
        maxEce={0.05}
        overrideReason="diagnostic only"
      />,
    );
    expect(container.querySelector('.calibration-over')).not.toBeNull();
    expect(screen.getByText('CAL OVERRIDE')).toBeInTheDocument();
  });

  it('CalibrationBadge handles unknown ECE', () => {
    const { container } = render(
      <CalibrationBadge ece={null} maxEce={undefined} />,
    );
    expect(container.querySelector('.calibration-unknown')).not.toBeNull();
    expect(screen.getByText('CAL UNKNOWN')).toBeInTheDocument();
  });
});
