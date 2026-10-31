"use client";

import type { JarvisState } from "@/lib/api";

const LOOK: Record<JarvisState, { label: (preset: string | null) => string; color: string }> = {
  off: { label: () => "ปิดอยู่", color: "bg-slate-700 text-slate-400" },
  idle: { label: () => "กดเพื่อพูด", color: "bg-emerald-600 text-white hover:bg-emerald-500" },
  listening: { label: () => "กำลังฟัง… (กดเพื่อหยุด)", color: "bg-red-600 text-white listening-ring" },
  transcribing: { label: () => "กำลังแปลงเสียง", color: "bg-amber-500 text-slate-900" },
  running: { label: (preset) => `กำลังทำ: ${preset ?? "…"}`, color: "bg-blue-600 text-white" },
};

interface Props {
  state: JarvisState;
  preset: string | null;
  disabled?: boolean;
  onPress: () => void;
}

/** Only `idle` and `listening` can be pressed: off is disabled, and the rest are busy. */
export default function MicButton({ state, preset, disabled, onPress }: Props) {
  const look = LOOK[state];
  const pressable = (state === "idle" || state === "listening") && !disabled;
  return (
    <div className="flex flex-col items-center gap-4">
      <button
        type="button"
        onClick={onPress}
        disabled={!pressable}
        aria-label={look.label(preset)}
        className={`flex h-40 w-40 items-center justify-center rounded-full shadow-lg transition-colors focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400 disabled:cursor-not-allowed ${look.color}`}
      >
        <svg viewBox="0 0 24 24" className="h-16 w-16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </button>
      <p className="min-h-7 text-center text-lg font-medium" aria-live="polite">
        {look.label(preset)}
      </p>
    </div>
  );
}
