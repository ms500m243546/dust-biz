// Pure aggregations over API payloads. Lives outside views so the math
// is testable and so the views stay declarative (ui-principles.md "no
// business logic in components"). When the backend grows real KPI
// endpoints in Phase K, these functions are replaced by direct fetches
// without touching the views.

import type {
  ActionOutcomeSchema,
  DustForecastSchema,
  RecommendationApprovalSchema,
  RecommendationSchema,
} from './types';

const EFFECTIVENESS_WEIGHT: Record<ActionOutcomeSchema['intervention_effectiveness'], number> = {
  successful: 1.0,
  partial: 0.5,
  unsuccessful: 0.0,
  not_applicable: 0.0,
};

export interface OperationsKpis {
  approvedCount: number;
  tonnesDelayed: number;
  avgEffectiveness: number;     // 0..1
  tonnesProtected: number;      // tonnesDelayed * avgEffectiveness
  shutdownsAvoided: number;
}

export function operationsKpis(
  recs: readonly RecommendationSchema[],
  approvals: readonly RecommendationApprovalSchema[],
  outcomes: readonly ActionOutcomeSchema[],
): OperationsKpis {
  const approved = approvals.filter((a) => a.approval_status === 'approved');
  const approvedRecIds = new Set(approved.map((a) => a.recommendation_id));
  const tonnesDelayed = recs
    .filter((r) => approvedRecIds.has(r.recommendation_id))
    .reduce((sum, r) => sum + (r.recommended_actions[0]?.estimated_tonnes_delayed ?? 0), 0);
  const avgEffectiveness = outcomes.length === 0 ? 0
    : outcomes.reduce((s, o) => s + EFFECTIVENESS_WEIGHT[o.intervention_effectiveness], 0) / outcomes.length;
  return {
    approvedCount: approved.length,
    tonnesDelayed,
    avgEffectiveness,
    tonnesProtected: tonnesDelayed * avgEffectiveness,
    shutdownsAvoided: approved.length,
  };
}

export interface ExecutiveKpis {
  decisionsMade: number;        // approve + override
  netEventExposure: number;     // events − approved decisions, floored at 0
  avgEffectiveness: number;
}

export function executiveKpis(
  approvals: readonly RecommendationApprovalSchema[],
  eventCount: number,
  outcomes: readonly ActionOutcomeSchema[],
): ExecutiveKpis {
  const approved = approvals.filter((a) => a.approval_status === 'approved').length;
  const overridden = approvals.filter((a) => a.approval_status === 'overridden').length;
  const avgEffectiveness = outcomes.length === 0 ? 0
    : outcomes.reduce((s, o) => s + EFFECTIVENESS_WEIGHT[o.intervention_effectiveness], 0) / outcomes.length;
  return {
    decisionsMade: approved + overridden,
    netEventExposure: Math.max(eventCount - approved, 0),
    avgEffectiveness,
  };
}

export interface ComplianceKpis {
  windowSize: number;
  avgPm10: number;
  avgPm25: number;
  forecastBreaches: number;     // count of forecasts with predicted_pm10 >= threshold
}

export function complianceKpis(
  forecasts: readonly DustForecastSchema[],
  pm10Threshold: number,
): ComplianceKpis {
  if (forecasts.length === 0) {
    return { windowSize: 0, avgPm10: 0, avgPm25: 0, forecastBreaches: 0 };
  }
  let sum10 = 0;
  let sum25 = 0;
  let breaches = 0;
  for (const f of forecasts) {
    sum10 += f.predicted_pm10;
    sum25 += f.predicted_pm25;
    if (f.predicted_pm10 >= pm10Threshold) breaches += 1;
  }
  return {
    windowSize: forecasts.length,
    avgPm10: sum10 / forecasts.length,
    avgPm25: sum25 / forecasts.length,
    forecastBreaches: breaches,
  };
}
