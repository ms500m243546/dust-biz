export interface UserSchema {
  user_id: string;
  username: string;
  role: 'shift_supervisor' | 'env_manager' | 'ops_manager' | 'executive' | 'admin';
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: UserSchema;
}

export interface ForecastTargetSchema {
  target_type: 'zone' | 'sensor';
  target_id: string;
}

export interface DustForecastSchema {
  prediction_id: string;
  target: ForecastTargetSchema;
  issued_at: string;
  horizon_minutes: number;
  pm10_predicted: number | null;
  pm25_predicted: number | null;
  breach_probability: number;
  risk_class: 'low' | 'medium' | 'high';
  confidence: number;
  reason: string;
  model_version: string;
  feature_pipeline_version: string;
  input_data_quality_score: number;
  missing_inputs: string[];
  data_quality_warnings: string[];
  source: string;
}

export interface ProbableSourceSchema {
  source_type: string;
  source_id: string;
  contribution_estimate: number;
  confidence: number;
  reason: string;
}

export interface SourceAttributionSchema {
  attribution_id: string;
  dust_event_id: string;
  target_id: string;
  probable_sources: ProbableSourceSchema[];
  confidence: number;
  model_version: string;
  reason: string;
  evidence_fields: Record<string, unknown>;
  created_at: string;
}

export interface RecommendationActionSchema {
  intervention_id: string;
  description: string;
  estimated_dust_reduction: number;
  estimated_tonnes_delayed: number;
  estimated_time_to_effect_minutes: number;
  confidence: number;
  reason: string;
  risk_class: 'low' | 'medium' | 'high';
  requires_human_approval: boolean;
}

export interface RecommendationSchema {
  recommendation_id: string;
  zone_id: string;
  issued_at: string;
  primary_action: RecommendationActionSchema;
  alternatives: RecommendationActionSchema[];
  confidence: number;
  reason: string;
  model_version: string;
  feature_pipeline_version: string;
  input_data_quality_score: number;
  linked_prediction_ids: string[];
  linked_attribution_id: string | null;
  requires_human_review: boolean;
  compliance_priority_triggered: boolean;
}

export interface RecommendationApprovalSchema {
  approval_id: string;
  recommendation_id: string;
  approval_status: 'approved' | 'rejected' | 'overridden' | 'expired';
  approved_by: string | null;
  decided_at: string;
  override_action: string | null;
  override_reason: string | null;
  confidence: number;
  reason: string;
  model_version: string;
}

export interface MineStateZoneSchema {
  zone_id: string;
  activity_summary: string;
  equipment_active: string[];
  dust_generation_potential: number;
  wind_exposure: 'low' | 'moderate' | 'high';
  downwind_assets: string[];
  staleness_flags: string[];
}

export interface MineStateSchema {
  mine_id: string;
  computed_at: string;
  zones: MineStateZoneSchema[];
  staleness_flags: string[];
}

export interface SensorHealthSchema {
  sensor_id: string;
  data_quality_score: number;
  status: 'ok' | 'degraded' | 'offline' | 'stale';
  reasons: string[];
  last_reading_at: string | null;
}

export interface AuditLogEntry {
  audit_id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ActionOutcomeSchema {
  outcome_id: string;
  recommendation_id: string;
  prediction_id: string | null;
  observed_pm10: number | null;
  observed_pm25: number | null;
  intervention_effectiveness: number;
  notes: string | null;
  recorded_by: string;
  recorded_at: string;
}

export interface DustEventSchema {
  event_id: string;
  zone_id: string | null;
  sensor_id: string | null;
  event_source: string;
  detected_at: string;
  severity: string;
  linked_prediction_ids: string[];
}

export interface SensorSchema {
  sensor_id: string;
  mine_id: string;
  zone_id: string | null;
  sensor_type: string;
  lat: number | null;
  lon: number | null;
}

export interface ZoneSchema {
  zone_id: string;
  mine_id: string;
  zone_type: string;
  geometry: Record<string, unknown> | null;
}
