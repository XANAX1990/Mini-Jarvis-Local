"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getState, type StateResponse } from "./api";

const POLL_MS = 500;

interface JarvisValue {
  data: StateResponse | null;
  /** null until the first answer; false when the API can't be reached */
  reachable: boolean | null;
  refresh: () => Promise<void>;
}

const JarvisContext = createContext<JarvisValue>({ data: null, reachable: null, refresh: async () => {} });

export const useJarvis = () => useContext(JarvisContext);

/** Polls GET /api/state every 500 ms (simple and enough on localhost); one poll shared by every page. */
export function JarvisProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<StateResponse | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setData(await getState());
      setReachable(true);
    } catch {
      setReachable(false);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    const tick = () => {
      if (!document.hidden) void refresh();
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [refresh]);

  const value = useMemo(() => ({ data, reachable, refresh }), [data, reachable, refresh]);
  return <JarvisContext.Provider value={value}>{children}</JarvisContext.Provider>;
}
