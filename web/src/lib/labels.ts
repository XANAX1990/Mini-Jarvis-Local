import type { JarvisState, Result } from "./api";

export const RESULT_LABEL: Record<Result, string> = {
  ok: "สำเร็จ",
  no_match: "ไม่เข้าใจ",
  no_speech: "ไม่ได้ยิน",
  error: "ผิดพลาด",
};

export const STATE_DOT: Record<JarvisState, string> = {
  off: "bg-slate-500",
  idle: "bg-emerald-500",
  listening: "bg-red-500 animate-pulse",
  transcribing: "bg-amber-400",
  running: "bg-blue-500",
};

export const STATE_NAME: Record<JarvisState, string> = {
  off: "ปิดอยู่",
  idle: "พร้อม",
  listening: "กำลังฟัง",
  transcribing: "กำลังแปลงเสียง",
  running: "กำลังทำ",
};

/** "2026-10-31T21:39:41+07:00" -> "21:39:41" (the server already writes Bangkok time). */
export const clock = (iso: string | null | undefined) => (iso ? iso.slice(11, 19) : "—");
