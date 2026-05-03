import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EvidenceDistribution, evidenceDistribution } from '../components/EvidenceDistribution';
import type { SourceAttributionSchema } from '../api/types';

function attr(evidence_class: SourceAttributionSchema['evidence_class']): SourceAttributionSchema {
  return {
    attribution_id: `att-${Math.random()}`,
    dust_event_id: 'evt',
    issued_at: '2026-05-03T12:00:00Z',
    affected_station: 'lp-em05-cuncumen',
    probable_sources: [],
    evidence_fields: {},
    confidence: 0.7,
    model_version: 'v0.1',
    evidence_class,
  };
}

describe('evidenceDistribution helper', () => {
  it('returns all-zero counts when input is null', () => {
    const counts = evidenceDistribution(null);
    expect(counts.experimental).toBe(0);
    expect(counts.quasi_experimental).toBe(0);
    expect(counts.observational_correlational).toBe(0);
    expect(counts.expert_judgment).toBe(0);
  });

  it('counts attributions by class', () => {
    const counts = evidenceDistribution([
      attr('quasi_experimental'),
      attr('quasi_experimental'),
      attr('observational_correlational'),
      attr('expert_judgment'),
    ]);
    expect(counts.quasi_experimental).toBe(2);
    expect(counts.observational_correlational).toBe(1);
    expect(counts.expert_judgment).toBe(1);
    expect(counts.experimental).toBe(0);
  });
});

describe('EvidenceDistribution component', () => {
  it('renders empty state when no attributions', () => {
    render(<EvidenceDistribution attributions={null} />);
    expect(screen.getByText(/No attributions yet/)).toBeInTheDocument();
  });

  it('renders empty state when attributions is empty array', () => {
    render(<EvidenceDistribution attributions={[]} />);
    expect(screen.getByText(/No attributions yet/)).toBeInTheDocument();
  });

  it('renders bar segments only for non-zero classes', () => {
    const { container } = render(
      <EvidenceDistribution
        attributions={[
          attr('quasi_experimental'),
          attr('observational_correlational'),
        ]}
      />,
    );
    const segments = container.querySelectorAll('.evidence-bar-segment');
    expect(segments).toHaveLength(2);
  });

  it('legend always shows all four classes', () => {
    render(<EvidenceDistribution attributions={[attr('quasi_experimental')]} />);
    expect(screen.getByText('EXPERIMENTAL')).toBeInTheDocument();
    expect(screen.getByText('QUASI-EXP.')).toBeInTheDocument();
    expect(screen.getByText('OBSERVATIONAL')).toBeInTheDocument();
    expect(screen.getByText('EXPERT JUDG.')).toBeInTheDocument();
  });
});
