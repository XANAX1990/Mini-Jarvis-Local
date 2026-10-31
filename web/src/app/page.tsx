"use client";

import { useState } from "react";
import LastCommand from "@/components/LastCommand";
import MicButton from "@/components/MicButton";
import RecentLog from "@/components/RecentLog";
import { setArmed, toggleListen } from "@/lib/api";
import { useJarvis } from "@/lib/jarvis";

export default function Home() {
  const { data, reachable, refresh } = useJarvis();
  const [problem, setProblem] = useState<string | null>(null);

  if (reachable === false) {
    return (
      <div role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center">
        <p className="text-lg font-semibold text-red-200">Jarvis ไม่ได้เปิดอยู่</p>
        <p className="mt-2 text-sm text-red-300/80">
          เปิดด้วย <code className="rounded bg-slate-900 px-1.5 py-0.5">python -m jarvis listen</code> แล้วหน้านี้จะต่อเองอัตโนมัติ
        </p>
      </div>
    );
  }
  if (!data) return <p className="text-center text-slate-500">กำลังเชื่อมต่อ…</p>;

  const act = async (action: () => Promise<unknown>) => {
    setProblem(null);
    try {
      await action();
    } catch {
      setProblem("สั่งไม่สำเร็จ ลองใหม่อีกครั้ง");
    }
    await refresh();
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col items-center gap-5 py-4">
        <MicButton state={data.state} preset={data.preset} onPress={() => act(toggleListen)} />

        <label className="flex cursor-pointer items-center gap-3 select-none">
          <span className="text-sm text-slate-300">Jarvis ฟังอยู่</span>
          <button
            type="button"
            role="switch"
            aria-checked={data.armed}
            onClick={() => act(() => setArmed(!data.armed))}
            className={`relative h-7 w-12 rounded-full transition-colors focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400 ${
              data.armed ? "bg-emerald-600" : "bg-slate-600"
            }`}
          >
            <span
              className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${data.armed ? "left-6" : "left-1"}`}
            />
            <span className="sr-only">{data.armed ? "เปิด" : "ปิด"}</span>
          </button>
          <span className="w-10 text-sm text-slate-400">{data.armed ? "เปิด" : "ปิด"}</span>
        </label>

        {data.armed && (
          <p className="text-sm text-slate-400">
            หรือกดปุ่ม <kbd className="rounded border border-slate-600 bg-slate-800 px-2 py-0.5 text-slate-200">{data.hotkey}</kbd>
          </p>
        )}
        {problem && (
          <p role="alert" className="text-sm text-red-400">
            {problem}
          </p>
        )}
      </div>

      <LastCommand last={data.last} />
      <RecentLog refreshKey={data.last?.time ?? ""} />
    </div>
  );
}
