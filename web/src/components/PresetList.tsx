"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getPresets, type PresetData } from "@/lib/api";
import { useJarvis } from "@/lib/jarvis";

export default function PresetList() {
  const { reachable } = useJarvis();
  const [presets, setPresets] = useState<PresetData[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPresets()
      .then((r) => !cancelled && setPresets(r.presets))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Presets</h1>
        <Link href="/presets/edit/" className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500">
          + เพิ่ม preset
        </Link>
      </div>

      {reachable === false || failed ? (
        <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center text-red-200">
          Jarvis ไม่ได้เปิดอยู่
        </p>
      ) : presets === null ? (
        <p className="text-slate-500">กำลังโหลด…</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {presets.map((p) => (
            <li key={p.name}>
              <Link
                href={`/presets/edit/?name=${encodeURIComponent(p.name)}`}
                className="block rounded-xl border border-slate-800 bg-slate-900/60 p-4 hover:border-sky-700"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-base font-semibold">{p.name}</span>
                  <span className="text-sm text-slate-500">{p.actions.length} ขั้นตอน</span>
                </div>
                <ul className="mt-2 flex flex-wrap gap-2" aria-label="วลีที่พูด">
                  {p.phrases.map((phrase) => (
                    <li key={phrase} className="rounded-full bg-slate-800 px-3 py-1 text-sm">
                      {phrase}
                    </li>
                  ))}
                </ul>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
