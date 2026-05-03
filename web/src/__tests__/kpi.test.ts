import { describe, expect, it } from 'vitest';
import { complianceKpis, executiveKpis, operationsKpis } from '../api/kpi';
import type {
  ActionOutcomeSchema,
  DustForecastSchema,
  RecommendationApprovalSchema,
  RecommendationSchema,
} from '../api/types';

function rec(id: string, tonnes = 100): RecommendationSchema {
  return {
    recommendation_id: id,
    issued_at: '',
    target_zone_id: 'Z',
    risk_event: '',
    current_breach_probability: 0,
    target_probability: 0,
    recommended_actions: [{
      rank: 1, intervention_id: 'water_road', action: 'water',
      breach_probability_after: 0, production_loss: 'low',
      estimated_tonnes_delayed: tonnes, confidence: 0.7,
      reason: '', requires_human_approval: false, risk_class: 'low',
      simulation_id: '',
    }],
    requires_human_review: false, compliance_priority_triggered: false,
    confidence: 0.7, reason: '', model_version: 'v1', feature_pipeline_version: 'v1',
    input_data_quality_score: 1, data_quality_warnings: [], linked_prediction_ids: [],
    linked_attribution_id: null, automation_level: 'L1', top_production_impact: null,
    causal_confidence: 0.5,
  };
}

function approval(recId: string, status: RecommendationApprovalSchema['approval_status']): RecommendationApprovalSchema {
  return {
    approval_id: 'A', recommendation_id: recId, approved_by: 'u', approver_role: 'admin',
    decided_at: '', approval_status: status, chosen_action_rank: 1, override_action: null,
    human_reason: null, automation_level_at_decision: 'L1',
    confidence: 0.7, reason: '', model_version: 'v1',
  };
}

function outcome(eff: ActionOutcomeSchema['intervention_effectiveness']): ActionOutcomeSchema {
  return {
    outcome_id: 1, recommendation_id: null, prediction_id: null,
    actual_pm10_peak: 0, actual_pm25_peak: null, breach_occurred: false,
    production_loss_tonnes_actual: null, intervention_effectiveness: eff,
    model_error: null, recorded_at: '', recorded_by: 'u',
  };
}

describe('kpi aggregations', () => {
  it('operationsKpis sums tonnes only across approved-recommendation rows', () => {
    const recs = [rec('R1', 100), rec('R2', 50), rec('R3', 200)];
    const approvals = [approval('R1', 'approved'), approval('R2', 'rejected'), approval('R3', 'approved')];
    const outcomes = [outcome('successful'), outcome('partial')];
    const k = operationsKpis(recs, approvals, outcomes);
    expect(k.approvedCount).toBe(2);
    expect(k.tonnesDelayed).toBe(300);
    expect(k.avgEffectiveness).toBe(0.75);
    expect(k.tonnesProtected).toBe(225);
    expect(k.shutdownsAvoided).toBe(2);
  });

  it('operationsKpis returns zeros on empty input', () => {
    const k = operationsKpis([], [], []);
    expect(k).toEqual({ approvedCount: 0, tonnesDelayed: 0, avgEffectiveness: 0, tonnesProtected: 0, shutdownsAvoided: 0 });
  });

  it('executiveKpis counts approve+override and floors net exposure at 0', () => {
    const approvals = [approval('R1', 'approved'), approval('R2', 'overridden'), approval('R3', 'rejected')];
    const k = executiveKpis(approvals, 1, [outcome('successful')]);
    expect(k.decisionsMade).toBe(2);
    expect(k.netEventExposure).toBe(0);
    expect(k.avgEffectiveness).toBe(1);
  });

  it('complianceKpis counts breaches and averages PM', () => {
    const f = (pm10: number, pm25: number): DustForecastSchema => ({
      issued_at: '', target_kind: 'zone', target_id: 'Z', forecast_horizon: '15min',
      predicted_pm10: pm10, predicted_pm25: pm25, breach_probability: 0,
      confidence: 1, main_risk_window: '', main_uncertainty: '', model_version: 'v1',
      feature_pipeline_version: 'v1', input_data_quality_score: 1,
      data_quality_warnings: [], source: 'model', input_record_ids: [],
    });
    const k = complianceKpis([f(40, 10), f(60, 20), f(80, 30)], 50);
    expect(k.windowSize).toBe(3);
    expect(k.avgPm10).toBe(60);
    expect(k.avgPm25).toBe(20);
    expect(k.forecastBreaches).toBe(2);
  });
});
