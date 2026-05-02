import type {
  TokenResponse,
  UserSchema,
  DustForecastSchema,
  SourceAttributionSchema,
  RecommendationSchema,
  RecommendationApprovalSchema,
  MineStateSchema,
  SensorHealthSchema,
  AuditLogEntry,
  ActionOutcomeSchema,
  DustEventSchema,
  ZoneSchema,
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
  mineStateCurrent: (params?: { mine_id?: string }) => {
    const q = params?.mine_id ? `?mine_id=${encodeURIComponent(params.mine_id)}` : '';
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
  approve: (recId: string) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/approve`, { method: 'POST' }),
  reject: (recId: string, reason: string) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  override: (recId: string, override_action: string, override_reason: string) =>
    request<RecommendationApprovalSchema>(`/recommendations/${recId}/override`, {
      method: 'POST',
      body: JSON.stringify({ override_action, override_reason }),
    }),
  approvals: () => request<RecommendationApprovalSchema[]>('/approvals'),
  sweepExpired: () =>
    request<{ swept: number }>('/approvals/sweep-expired', { method: 'POST' }),

  // dust events
  dustEvents: () => request<DustEventSchema[]>('/dust-events'),

  // data quality
  sensorHealth: () => request<SensorHealthSchema[]>('/data-quality'),

  // outcomes
  outcomes: () => request<ActionOutcomeSchema[]>('/action-outcomes'),
  recordOutcome: (body: {
    recommendation_id: string;
    prediction_id?: string | null;
    observed_pm10?: number | null;
    observed_pm25?: number | null;
    intervention_effectiveness: number;
    notes?: string;
  }) =>
    request<ActionOutcomeSchema>('/action-outcomes', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // zones
  zones: () => request<ZoneSchema[]>('/zones'),

  // audit (read via meta endpoint isn't exposed yet; surface via approvals + outcomes histories)
  // Phase J reads audit-relevant rows from /approvals + /action-outcomes + /dust-events.
  auditFromApprovalsAndOutcomes: async (): Promise<AuditLogEntry[]> => {
    const [approvals, outcomes] = await Promise.all([
      request<RecommendationApprovalSchema[]>('/approvals'),
      request<ActionOutcomeSchema[]>('/action-outcomes').catch(() => [] as ActionOutcomeSchema[]),
    ]);
    const a: AuditLogEntry[] = approvals.map((row, i) => ({
      audit_id: i,
      actor: row.approved_by ?? 'system',
      action: row.approval_status,
      entity_type: 'recommendation',
      entity_id: row.recommendation_id,
      payload: { override_action: row.override_action, override_reason: row.override_reason },
      created_at: row.decided_at,
    }));
    const o: AuditLogEntry[] = outcomes.map((row, i) => ({
      audit_id: 1_000_000 + i,
      actor: row.recorded_by,
      action: 'outcome_recorded',
      entity_type: 'action_outcome',
      entity_id: row.outcome_id,
      payload: {
        intervention_effectiveness: row.intervention_effectiveness,
        observed_pm10: row.observed_pm10,
      },
      created_at: row.recorded_at,
    }));
    return [...a, ...o].sort((x, y) => y.created_at.localeCompare(x.created_at));
  },
};
