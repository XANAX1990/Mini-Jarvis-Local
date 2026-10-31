"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, addPhrase, getLogDates, getLogs, getPresets, type LogEntry, type PresetData, type Result } from "@/lib/api";
import { thaiError } from "@/lib/errors";
import { useJarvis } from "@/lib/jarvis";
import { RESULT_LABEL, clock } from "@/lib/labels";

type Filter = Result | "all";
const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "ทั้งหมด" },
  { value: "ok", label: RESULT_LABEL.ok },
  { value: "no_match", label: RESULT_LABEL.no_match },
  { value: "no_speech", label: RESULT_LABEL.no_speech },
  { value: "error", label: RESULT_LABEL.error },
];

const RESULT_COLOR: Record<Result, string> = {
  ok: "text-emerald-400",
  no_match: "text-amber-400",
  no_speech: "text-slate-400",
  error: "text-red-400",
};

const field =
  "rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500";

export default function LogView() {
  const { data, reachable } = useJarvis();
  const refreshKey = data?.last?.time ?? ""; // a command just finished: reload today's lines

  const [day, setDay] = useState<string>(""); // "" = today, as the server knows it
  const [shownDay, setShownDay] = useState("");
  const [dates, setDates] = useState<string[]>([]);
  const [entries, setEntries] = useState<LogEntry[] | null>(null);
  const [presets, setPresets] = useState<PresetData[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getLogs(day || undefined), getLogDates()])
      .then(([logs, d]) => {
        if (cancelled) return;
        setShownDay(logs.date);
        setEntries(logs.entries.slice().reverse()); // newest first
        setDates(d.dates);
        setFailed(false);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [day, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    getPresets()
      .then((r) => !cancelled && setPresets(r.presets))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const days = useMemo(() => (shownDay && !dates.includes(shownDay) ? [shownDay, ...dates] : dates), [dates, shownDay]);
  const rows = useMemo(() => (entries ?? []).filter((e) => filter === "all" || e.result === filter), [entries, filter]);

  if (reachable === false || failed) {
    return (
      <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center text-red-200">
        Jarvis ไม่ได้เปิดอยู่
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Log</h1>

      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor="log-day" className="mb-1 block text-sm text-slate-300">
            วันที่ (เฉพาะวันที่มี log)
          </label>
          <select id="log-day" value={shownDay} onChange={(e) => setDay(e.target.value)} className={field}>
            {days.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="log-filter" className="mb-1 block text-sm text-slate-300">
            ผลลัพธ์
          </label>
          <select id="log-filter" value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className={field}>
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {entries === null ? (
        <p className="text-slate-500">กำลังโหลด…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500">{entries.length === 0 ? "วันนี้ยังไม่มีคำสั่ง" : "ไม่มีรายการตามตัวกรองนี้"}</p>
      ) : (
        <div className="relative overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">เวลา</th>
                <th scope="col" className="px-3 py-2 font-medium">ได้ยินว่า</th>
                <th scope="col" className="px-3 py-2 font-medium">Preset</th>
                <th scope="col" className="px-3 py-2 font-medium">คะแนน</th>
                <th scope="col" className="px-3 py-2 font-medium">ผล</th>
                <th scope="col" className="px-3 py-2"><span className="sr-only">การทำงาน</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((e) => (
                <LogRow key={e.id} entry={e} presets={presets} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LogRow({ entry, presets }: { entry: LogEntry; presets: PresetData[] }) {
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState(entry.preset ?? ""); // "" until picked: then the first preset
  const selected = choice || presets[0]?.name || "";
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const canAdd = entry.transcript.trim() !== "" && entry.source !== "test" && presets.length > 0;

  const submit = useCallback(async () => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await addPhrase(entry.id, selected);
      setMessage({
        ok: true,
        text: r.added
          ? `เพิ่มแล้วใน ${selected} พูดประโยคนี้ได้เลย${r.warnings.length ? ` (คล้ายกับวลีใน ${r.warnings[0].preset})` : ""}`
          : `มีวลีนี้ใน ${selected} อยู่แล้ว`,
      });
    } catch (e) {
      setMessage({
        ok: false,
        text: e instanceof ApiError && e.fields.length ? thaiError(e.fields[0].message) : "เพิ่มไม่สำเร็จ ลองใหม่อีกครั้ง",
      });
    } finally {
      setBusy(false);
    }
  }, [entry.id, selected]);

  return (
    <Fragment>
      <tr>
        <td className="px-3 py-2 tabular-nums text-slate-500">{clock(entry.time)}</td>
        <td className="px-3 py-2 break-words">{entry.transcript || "—"}</td>
        <td className="px-3 py-2 text-slate-300">{entry.preset ?? "—"}</td>
        <td className="px-3 py-2 tabular-nums">{entry.score == null ? "—" : Math.round(entry.score)}</td>
        <td className={`px-3 py-2 ${RESULT_COLOR[entry.result]}`}>{RESULT_LABEL[entry.result]}</td>
        <td className="px-3 py-2 text-right">
          {canAdd && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="rounded-lg border border-slate-600 px-3 py-1 text-xs text-sky-300 hover:bg-slate-800"
            >
              เพิ่มเป็นวลี
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="bg-slate-900/60">
          <td colSpan={6} className="px-3 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-slate-300">
                เพิ่ม &quot;{entry.transcript}&quot; เป็นวลีของ
              </span>
              <select aria-label="เลือก preset" value={selected} onChange={(e) => setChoice(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm">
                {presets.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => void submit()} disabled={busy || !selected} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
                เพิ่ม
              </button>
              <button type="button" onClick={() => setOpen(false)} className="text-sm text-slate-400 hover:text-slate-200">
                ปิด
              </button>
            </div>
            {message && (
              <p role={message.ok ? "status" : "alert"} className={`mt-2 text-sm ${message.ok ? "text-emerald-300" : "text-red-400"}`}>
                {message.text}
              </p>
            )}
          </td>
        </tr>
      )}
    </Fragment>
  );
}
