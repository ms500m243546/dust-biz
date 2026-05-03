// Wire types - match backend Pydantic schemas exactly. When a backend
// schema changes, this file is the single point of update on the web
// side; everything downstream (client.ts, kpi.ts, views) is typed.

export type Role =
  | 'shift_supervisor'
  | 'environmental_manager'
  | 'operations_manager'
  | 'dispatcher'
  | 'executive'
  | 'admin';

export type RiskClass = 'low' | 'medium' | 'high';
export type ProductionLossLabel = 'low' | 'medium' | 'high';
export type ForecastHorizon = '15min' | '30min' | '60min' | '120min' | '24h';
export type ForecastSource = 'model' | 'heuristic_fallback';
export type TargetKind = 'sensor' | 'zone';
export type ApprovalStatus = 'approved' | 'rejected' | 'overridden' | 'expired';
export type SensorStatus = 'healthy' | 'degraded' | 'offline' | 'unknown';
export type InterventionEffectiveness =
  | 'successful'
  | 'partial'
  | 'unsuccessful'
  | 'not_applicable';
export type DustEventSource = 'model_alert' | 'manual_entry' | 'threshold_trigger';
export type ZoneActivity =
  | 'idle' | 'loading' | 'hauling' | 'dumping' | 'drilling'
  | 'crushing' | 'watering' | 'grading' | 'maintenance' | 'mixed' | 'unknown';
export type DustGenerationPotential = 'low' | 'medium' | 'high' | 'unknown';
export type WindExposure = 'low' | 'medium' | 'high' | 'unknown';

// M.3.1 — causal-protocol evidence class. Strongest -> weakest.
export type EvidenceClass =
  | 'experimental'
  | 'quasi_experimental'
  | 'observational_correlational'
  | 'expert_judgment';

// M.3.1 — causal-protocol simulation method.
export type SimulationMethod =
  | 'naive_correlation'
  | 'dispersion_model'
  | 'propensity_matched'
  | 'rct';

export interface UserSchema {
  user_id: string;
  username: string;
  role: Role;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  role: Role;
}

export interface DustForecastSchema {
  issued_at: string;
  target_kind: TargetKind;
  target_id: string;
  forecast_horizon: ForecastHorizon;
  predicted_pm10: number;
  predicted_pm25: number;
  breach_probability: number;
  confidence: number;
  main_risk_window: string;
  main_uncertainty: string;
  model_version: string;
  feature_pipeline_version: string;
  input_data_quality_score: number;
  data_quality_warnings: string[];
  source: ForecastSource;
  input_record_ids: string[];
}

export interface ProbableSource {
  source: string;
  confidence: number;
  reason: string;
}

export interface SourceAttributionSchema {
  attribution_id: string;
  dust_event_id: string;
  issued_at: string;
  affected_station: string;
  probable_sources: ProbableSource[];
  evidence_fields: Record<string, unknown>;
  confidence: number;
  model_version: string;
  // M.3.1 — see docs/causal-protocol.md.
  evidence_class: EvidenceClass;
}

export interface RecommendationActionSchema {
  rank: number;
  intervention_id: string;
  action: string;
  breach_probability_after: number;
  production_loss: ProductionLossLabel;
  estimated_tonnes_delayed: number;
  confidence: number;
  reason: string;
  requires_human_approval: boolean;
  risk_class: RiskClass;
  simulation_id: string;
}

export interface RecommendationSchema {
  recommendation_id: string;
  issued_at: string;
  target_zone_id: string;
  risk_event: string;
  current_breach_probability: number;
  target_probability: number;
  recommended_actions: RecommendationActionSchema[];
  requires_human_review: boolean;
  compliance_priority_triggered: boolean;
  confidence: number;
  reason: string;
  model_version: string;
  feature_pipeline_version: string;
  input_data_quality_score: number;
  data_quality_warnings: string[];
  linked_prediction_ids: string[];
  linked_attribution_id: string | null;
  automation_level: string;
  top_production_impact: string | null;
  // M.3.1 — penalty-adjusted causal confidence vs predictive `confidence`.
  causal_confidence: number;
}

export interface InterventionSimulationSchema {
  simulation_id: string;
  requested_at: string;
  intervention_id: string;
  target_zone_id: string;
  scenario: string;
  predicted_pm10_reduction: number;
  predicted_pm25_reduction: number | null;
  breach_probability_before: number;
  breach_probability_after: number;
  time_to_effect_minutes: number;
  production_loss_tonnes: number;
  cycle_time_increase_percent: number;
  production_impact: 'low' | 'medium' | 'high';
  confidence: number;
  model_version: string;
  cost_model_version: string;
  source: 'model' | 'heuristic';
  main_uncertainty: string | null;
  // M.3.1.
  simulation_method: SimulationMethod;
  counterfactual_assumption: string;
  selection_bias_caveat: boolean;
}

// M.4.1 — calibration reliability bin (10-bin reliability table).
export interface CalibrationBin {
  lower: number;
  upper: number;
  count: number;
  avg_predicted: number;
  actual_frequency: number;
}

export interface ModelPerformanceMetricSchema {
  metric_id: number;
  model_version: string;
  model_kind: string;
  evaluated_at: string;
  window_from: string;
  window_to: string;
  sample_count: number;
  metric_payload: {
    sample_count?: number;
    observed_count?: number;
    mae_pm10?: number | null;
    breach_precision?: number | null;
    breach_recall?: number | null;
    calibration_error?: number | null;
    // M.4.1.
    calibration_bins?: CalibrationBin[];
    ece?: number | null;
    brier_score?: number | null;
    avoided_shutdowns_estimate?: number;
    production_loss_tonnes_total?: number;
    protocol?: {
      protocol_version?: string;
      protocol_hash?: string;
      split_strategy?: string;
      max_ece?: number;
      warnings?: string[];
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
}

export interface RecommendationApprovalSchema {
  approval_id: string;
  recommendation_id: string;
  approved_by: string;
  approver_role: string;
  decided_at: string;
  approval_status: ApprovalStatus;
  chosen_action_rank: number | null;
  override_action: string | null;
  human_reason: string | null;
  automation_level_at_decision: string;
  confidence: number;
  reason: string;
  model_version: string;
}

export interface MineStateZoneSchema {
  timestamp: string;
  zone_id: string;
  activity: ZoneActivity;
  equipment_active: string[];
  production_rate_tph: number | null;
  dust_generation_potential: DustGenerationPotential;
  wind_exposure: WindExposure;
  downwind_assets: string[];
  operational_importance: string;
  staleness_flags: string[];
}

export interface MineStateSchema {
  mine_id: string;
  computed_at: string;
  window_minutes: number;
  zones: MineStateZoneSchema[];
}

export interface SensorHealthStatusSchema {
  sensor_id: string;
  status: SensorStatus;
  quality_score: number;
  issues: string[];
  downstream_confidence_multiplier: number;
}

export interface AuditLogSchema {
  audit_id: number;
  occurred_at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
}

export interface ActionOutcomeSchema {
  outcome_id: number;
  recommendation_id: string | null;
  prediction_id: string | null;
  actual_pm10_peak: number;
  actual_pm25_peak: number | null;
  breach_occurred: boolean;
  production_loss_tonnes_actual: number | null;
  intervention_effectiveness: InterventionEffectiveness;
  model_error: string | null;
  recorded_at: string;
  recorded_by: string;
}

// M.4.3 — drift-watch alert. One per metric whose median crossed the
// per-metric threshold in DRIFT_THRESHOLDS between baseline and recent
// halves of the requested window.
export interface DriftAlertSchema {
  model_version: string;
  metric_name: string;
  baseline_value: number;
  recent_value: number;
  delta: number;
  threshold: number;
  baseline_sample_count: number;
  recent_sample_count: number;
  detected_at: string;
}

export interface DustEventSchema {
  event_id: string;
  detected_at: string;
  affected_station: string;
  peak_pm10: number;
  peak_pm25: number;
  breach_occurred: boolean;
  event_source: DustEventSource;
  linked_prediction_ids: string[];
  notes: string | null;
}
