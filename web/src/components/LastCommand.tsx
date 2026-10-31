import type { LastCommand as Last } from "@/lib/api";
import { RESULT_LABEL, clock } from "@/lib/labels";

export default function LastCommand({ last }: { last: Last | null }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4" aria-labelledby="last-title">
      <h2 id="last-title" className="mb-3 text-sm font-semibold text-slate-400">
        คำสั่งล่าสุด
      </h2>
      {last ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-slate-500">เวลา</dt>
          <dd>{clock(last.time)}</dd>
          <dt className="text-slate-500">ได้ยินว่า</dt>
          <dd className="break-words">{last.transcript || "—"}</dd>
          <dt className="text-slate-500">Preset</dt>
          <dd>{last.preset ?? "—"}</dd>
          <dt className="text-slate-500">คะแนน</dt>
          <dd>{last.score == null ? "—" : Math.round(last.score)}</dd>
          <dt className="text-slate-500">ผล</dt>
          <dd>{last.result ? RESULT_LABEL[last.result] : "—"}</dd>
        </dl>
      ) : (
        <p className="text-sm text-slate-500">ยังไม่มีคำสั่งตั้งแต่เปิด Jarvis</p>
      )}
    </section>
  );
}
