"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, getToken, getUser } from "./api";

export interface PollState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  lastUpdated: number | null;
}

/**
 * Poll a fetcher on an interval. Pauses while the tab is hidden, dedupes overlapping
 * calls, and keeps the last good value on transient errors.
 */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs = 5000, deps: unknown[] = [], enabled = true): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settled, setSettled] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const inflight = useRef(false);
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const refresh = useCallback(async () => {
    if (inflight.current || !enabled) return;
    inflight.current = true;
    try {
      const out = await fetcherRef.current();
      setData(out);
      setError(null);
      setLastUpdated(Date.now());
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.code}: ${e.message}` : e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setSettled(true);
      inflight.current = false;
    }
  }, [enabled]);

  // Timer-driven polling: `tick` is only ever invoked asynchronously (timeout /
  // interval / visibility event), never synchronously in the effect body.
  const tick = useCallback(() => {
    if (document.visibilityState === "visible") void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!enabled) return;
    const kick = setTimeout(tick, 0);
    const timer = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearTimeout(kick);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, enabled, tick, ...deps]);

  return { data, error, loading: enabled && !settled, refresh, lastUpdated };
}

// ---- session (external store: localStorage) ---------------------------------------------
const listeners = new Set<() => void>();
function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}
export function notifySession() {
  listeners.forEach((l) => l());
}
const tokenSnapshot = () => getToken();
const serverSnapshot = () => null;
const hydratedClient = () => true;
const hydratedServer = () => false;

export function useSession() {
  const token = useSyncExternalStore(subscribe, tokenSnapshot, serverSnapshot);
  const ready = useSyncExternalStore(subscribe, hydratedClient, hydratedServer);
  const user = token ? getUser() : null;
  return { token, user, ready };
}

export function useRequireAuth() {
  const s = useSession();
  useEffect(() => {
    if (s.ready && !s.token && !window.location.pathname.startsWith("/login")) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [s.ready, s.token]);
  return s;
}

export function useAsyncAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.message}` : e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run, clear: () => setError(null) };
}
