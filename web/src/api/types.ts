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
