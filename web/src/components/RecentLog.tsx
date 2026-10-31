"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getLogs, type LogEntry } from "@/lib/api";
import { RESULT_LABEL, clock } from "@/lib/labels";

const SHOWN = 5;

/** Today's last few log lines. Reloads when `refreshKey` changes (a new command finished). */
export default function RecentLog({ refreshKey }: { refreshKey: string }) {
  const [entries, setEntries] = useState<LogEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLogs()
      .then((r) => {
        if (!cancelled) setEntries(r.entries.slice(-SHOWN).reverse());
      })
      .catch(() => {
        if (!cancelled) setEntries(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4" aria-labelledby="recent-title">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="recent-title" className="text-sm font-semibold text-slate-400">
          วันนี้
        </h2>
        <Link href="/log/" className="text-sm text-sky-400 hover:underline">
          ดู Log ทั้งหมด
        </Link>
      </div>
      {entries === null ? (
        <p className="text-sm text-slate-500">กำลังโหลด…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-slate-500">วันนี้ยังไม่มีคำสั่ง</p>
      ) : (
        <ul className="divide-y divide-slate-800 text-sm">
          {entries.map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2">
              <span className="tabular-nums text-slate-500">{clock(e.time)}</span>
              <span className="min-w-0 flex-1 break-words">{e.transcript || "—"}</span>
              <span className="text-slate-400">{e.preset ?? ""}</span>
              <span className={e.result === "ok" ? "text-emerald-400" : "text-amber-400"}>{RESULT_LABEL[e.result]}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
