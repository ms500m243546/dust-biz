import { useEffect, useRef } from 'react';

export function usePolling(fn: () => void, ms: number, enabled = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => fnRef.current(), ms);
    return () => clearInterval(id);
  }, [ms, enabled]);
}
