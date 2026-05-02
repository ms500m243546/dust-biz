import { useCallback, useEffect, useRef, useState } from 'react';

interface ApiState<T> {
  data: T | null;
  error: Error | null;
  initialLoading: boolean;
  refreshing: boolean;
  reload: () => void;
  lastUpdated: Date | null;
}

// Subscribe to an API call; if `pollMs` is set, refresh in the background
// without flipping `initialLoading` (callers render skeletons only on the
// first call). `setData` short-circuits on byte-identical payloads to
// avoid downstream rerenders on no-op poll ticks.
export function useApi<T>(fn: () => Promise<T>, pollMs?: number): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const lastPayloadRef = useRef<string | null>(null);
  const isFirstRef = useRef(true);

  const reload = useCallback(() => {
    let cancelled = false;
    if (isFirstRef.current) setInitialLoading(true);
    else setRefreshing(true);
    fnRef.current()
      .then((d) => {
        if (cancelled) return;
        const serialized = JSON.stringify(d ?? null);
        if (serialized !== lastPayloadRef.current) {
          lastPayloadRef.current = serialized;
          setData(d);
        }
        setError(null);
        setLastUpdated(new Date());
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (cancelled) return;
        setInitialLoading(false);
        setRefreshing(false);
        isFirstRef.current = false;
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => reload(), [reload]);

  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(reload, pollMs);
    return () => clearInterval(id);
  }, [pollMs, reload]);

  return { data, error, initialLoading, refreshing, reload, lastUpdated };
}
