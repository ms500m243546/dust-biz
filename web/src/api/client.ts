import type {
  TokenResponse,
  UserSchema,
  DustForecastSchema,
  SourceAttributionSchema,
  RecommendationSchema,
  RecommendationApprovalSchema,
  MineStateSchema,
  SensorHealthStatusSchema,
  AuditLogSchema,
  ActionOutcomeSchema,
  DustEventSchema,
  InterventionEffectiveness,
  ModelPerformanceMetricSchema,
} from './types';

const TOKEN_KEY = 'dustops.token';

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, body);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try { return JSON.parse(text); } catch { return text; }
}

export const api = {
  // auth
  login: (username: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<UserSchema>('/auth/me'),

  // mine state
  mineStateCurrent: (mine_id?: string) => {
    const q = mine_id ? `?mine_id=${encodeURIComponent(mine_id)}` : '';
    return request<MineStateSchema>(`/mine-state/current${q}`);
  },

  // forecasts
  forecastsCurrent: () => request<DustForecastSchema | null>('/forecasts/current'),
  forecastsHistory: () => request<DustForecastSchema[]>('/forecasts/history'),

  // attributions
  attributions: () => request<SourceAttributionSchema[]>('/attributions'),

  // recommendations
  recommendationsCurrent: () => request<RecommendationSchema | null>('/recommendations/current'),
  recommendations: () => request<RecommendationSchema[]>('/recommendations'),
  recommendation: (id: string) => request<RecommendationSchema>(`/recommendations/${id}`),
  approval: (recId: string) => request<RecommendationApprovalSchema | null>(`/recommendations/${recId}/approval`),
  approve: (recId: string, body: { chosen_action_rank: number; human_reason?: string }) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/approve`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reject: (recId: string, human_reason: string) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ human_reason }),
    }),
  override: (recId: string, override_action: string, human_reason: string) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/override`, {
      method: 'POST',
      body: JSON.stringify({ override_action, human_reason }),
    }),
  approvals: () => request<RecommendationApprovalSchema[]>('/approvals'),
  sweepExpired: () =>
    request<RecommendationApprovalSchema[]>('/approvals/sweep-expired', { method: 'POST' }),

  // dust events
  dustEvents: () => request<DustEventSchema[]>('/dust-events'),

  // data quality
  sensorHealth: () => request<SensorHealthStatusSchema[]>('/data-quality'),

  // outcomes
  outcomes: () => request<ActionOutcomeSchema[]>('/action-outcomes'),
  recordOutcome: (body: {
    recommendation_id?: string | null;
    prediction_id?: string | null;
    actual_pm10_peak: number;
    actual_pm25_peak?: number | null;
    breach_occurred: boolean;
    production_loss_tonnes_actual?: number | null;
    intervention_effectiveness: InterventionEffectiveness;
    model_error?: string | null;
  }) =>
    request<ActionOutcomeSchema>('/action-outcomes', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // audit (real, server-side)
  audit: (params?: { since_minutes?: number; limit?: number; entity_type?: string; entity_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.since_minutes) q.set('since_minutes', String(params.since_minutes));
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.entity_type) q.set('entity_type', params.entity_type);
    if (params?.entity_id) q.set('entity_id', params.entity_id);
    const s = q.toString();
    return request<AuditLogSchema[]>(`/audit${s ? `?${s}` : ''}`);
  },

  modelPerformance: () =>
    request<ModelPerformanceMetricSchema[]>('/model-performance'),
};
