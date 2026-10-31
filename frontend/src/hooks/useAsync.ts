import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const run = useCallback(() => {
    const id = ++seq.current;
    setLoading(true); setError(null);
    fn().then((d) => { if (id === seq.current) setData(d); }).catch((e: Error) => { if (id === seq.current) setError(e.message); })
      .finally(() => { if (id === seq.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run, setData };
}

/** Poll `fn` every `ms` until `done(result)` returns true. */
export function usePoll<T>(fn: (() => Promise<T>) | null, done: (r: T) => boolean, ms = 1500) {
  const [value, setValue] = useState<T | null>(null);
  useEffect(() => {
    if (!fn) return;
    let stop = false;
    const tick = async () => {
      try { const r = await fn(); if (stop) return; setValue(r); if (!done(r)) setTimeout(tick, ms); } catch { if (!stop) setTimeout(tick, ms * 2); }
    };
    tick();
    return () => { stop = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fn]);
  return value;
}
