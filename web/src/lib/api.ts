// The one place that talks to the Jarvis API. Every request carries Content-Type and X-Jarvis:
// the API refuses anything else (see SECURITY.md, "Local web API").

export type JarvisState = "off" | "idle" | "listening" | "transcribing" | "running";
export type Result = "ok" | "no_match" | "no_speech" | "error";

export interface LastCommand {
  time: string | null;
  transcript: string | null;
  preset: string | null;
  score: number | null;
  result: Result | null;
}

export interface StateResponse {
  armed: boolean;
  state: JarvisState;
  hotkey: string;
  preset: string | null; // the preset being run, only while state is "running"
  last: LastCommand | null;
}

export interface LogEntry {
  id: string;
  time: string;
  source: "hotkey" | "web" | "test";
  transcript: string;
  preset: string | null;
  score: number | null;
  result: Result;
  seconds: number;
}

// Same origin in production (Python serves the web). `next dev` runs on :3004, so it calls :3003.
const BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:3003" : "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json", "X-Jarvis": "1" },
    body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    let code = "error";
    try {
      code = (await res.json()).error ?? code;
    } catch {
      // not JSON: keep the generic code
    }
    throw new ApiError(res.status, code);
  }
  return res.json() as Promise<T>;
}

export const getState = (signal?: AbortSignal) => request<StateResponse>("GET", "/api/state", undefined, signal);
export const setArmed = (armed: boolean) => request<StateResponse>("POST", "/api/armed", { armed });
export const toggleListen = () => request<{ accepted: boolean } & StateResponse>("POST", "/api/listen/toggle");
export const getLogs = (date?: string) =>
  request<{ date: string; entries: LogEntry[] }>("GET", date ? `/api/logs?date=${encodeURIComponent(date)}` : "/api/logs");
