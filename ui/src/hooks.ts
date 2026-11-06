import { useCallback, useEffect, useRef, useState } from "react";

/** Runs `fn` now and every `ms` while the window is visible; pauses when hidden, resumes on return. */
export function usePoll<T>(fn: () => Promise<T>, ms: number, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const tick = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => {
    if (!enabled) return;
    let timer: number | undefined;
    let alive = true;
    const loop = async () => {
      if (document.visibilityState === "visible") await tick();
      if (alive) timer = window.setTimeout(loop, ms);
    };
    loop();
    const onVis = () => document.visibilityState === "visible" && tick();
    document.addEventListener("visibilitychange", onVis);
    return () => { alive = false; clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [ms, enabled, tick]);
  return { data, error, refresh: tick };
}

/** One async action with its own busy and error state, for buttons. */
export function useAction<A extends unknown[], R>(fn: (...a: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = useCallback(async (...a: A) => {
    setBusy(true);
    setError(null);
    try {
      return await fn(...a);
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [fn]);
  return { run, busy, error, setError };
}

/** A value kept in localStorage, so the app reopens where the user left it. */
export function useStored<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => {
    try {
      const s = localStorage.getItem(key);
      return s == null ? initial : (JSON.parse(s) as T);
    } catch {
      return initial;
    }
  });
  const set = useCallback((next: T) => {
    setV(next);
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* storage off: keep in memory */ }
  }, [key]);
  return [v, set] as const;
}
