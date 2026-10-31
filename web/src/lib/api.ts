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

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public fields: FieldError[] = [],
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
    let fields: FieldError[] = [];
    try {
      const body = await res.json();
      code = body.error ?? code;
      fields = Array.isArray(body.fields) ? body.fields : [];
    } catch {
      // not JSON: keep the generic code
    }
    throw new ApiError(res.status, code, fields);
  }
  return res.json() as Promise<T>;
}

export const getState = (signal?: AbortSignal) => request<StateResponse>("GET", "/api/state", undefined, signal);
export const setArmed = (armed: boolean) => request<StateResponse>("POST", "/api/armed", { armed });
export const toggleListen = () => request<{ accepted: boolean } & StateResponse>("POST", "/api/listen/toggle");
export const getLogs = (date?: string) =>
  request<{ date: string; entries: LogEntry[] }>("GET", date ? `/api/logs?date=${encodeURIComponent(date)}` : "/api/logs");

// ---- presets ----

export type ActionData = { type: string } & Record<string, unknown>;

export interface PresetData {
  name: string;
  phrases: string[];
  reply: string;
  actions: ActionData[];
}

export interface ActionField {
  name: string;
  kind: "path" | "text" | "text-list" | "number" | "choice";
  required: boolean;
  min?: number;
  max?: number;
  options?: string[];
}

export interface ActionType {
  type: string;
  label: string;
  fields: ActionField[];
}

export interface PhraseWarning {
  phrase: string;
  preset: string;
  similar_to: string;
  score: number;
}

type PresetBody = Omit<PresetData, "name">;
const presetUrl = (name: string) => `/api/presets/${encodeURIComponent(name)}`;

export const getPresets = () => request<{ presets: PresetData[] }>("GET", "/api/presets");
export const getActionTypes = () => request<{ types: ActionType[] }>("GET", "/api/action-types");
export const createPreset = (preset: PresetData) =>
  request<{ name: string; warnings: PhraseWarning[] }>("POST", "/api/presets", preset);
export const replacePreset = (name: string, body: PresetBody) =>
  request<{ name: string; warnings: PhraseWarning[] }>("PUT", presetUrl(name), body);
export const deletePreset = (name: string) => request<{ name: string }>("DELETE", presetUrl(name));
export const testPreset = (name: string) => request<{ started: boolean }>("POST", `${presetUrl(name)}/test`);
