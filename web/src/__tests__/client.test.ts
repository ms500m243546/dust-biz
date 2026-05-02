import { describe, expect, it, vi, beforeEach } from 'vitest';
import { api, getToken, setToken, ApiError } from '../api/client';

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('persists and reads tokens via localStorage', () => {
    expect(getToken()).toBeNull();
    setToken('abc');
    expect(getToken()).toBe('abc');
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it('attaches Authorization header when token is set', async () => {
    setToken('tok-123');
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ user_id: 'u', username: 'me', role: 'admin', created_at: 'x' }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await api.me();
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = new Headers(call[1].headers);
    expect(headers.get('Authorization')).toBe('Bearer tok-123');
  });

  it('throws ApiError on non-2xx responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'nope' }), {
        status: 401, statusText: 'Unauthorized', headers: { 'Content-Type': 'application/json' },
      }),
    ));
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
  });
});
