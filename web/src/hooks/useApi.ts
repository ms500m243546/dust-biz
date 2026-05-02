import { useCallback, useEffect, useRef, useState } from 'react';

interface ApiState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  lastUpdated: Date | null;
}

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    fnRef.current()
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
        setLastUpdated(new Date());
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { return reload(); }, deps);

  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(reload, pollMs);
    return () => clearInterval(id);
  }, [pollMs, reload]);

  return { data, error, loading, reload, lastUpdated };
}
