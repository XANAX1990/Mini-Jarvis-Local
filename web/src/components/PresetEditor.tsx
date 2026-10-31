"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  createPreset,
  deletePreset,
  getActionTypes,
  getPresets,
  replacePreset,
  testPreset,
  type ActionData,
  type ActionType,
  type FieldError,
  type PhraseWarning,
  type PresetData,
} from "@/lib/api";
import { describeField, messagesFor, thaiError } from "@/lib/errors";
import { useJarvis } from "@/lib/jarvis";
import ActionEditor, { blankAction, cleanAction } from "./ActionEditor";
import TagInput from "./TagInput";

const NAME_RE = /^[a-z0-9-]{1,32}$/;
const EMPTY: PresetData = { name: "", phrases: [], reply: "", actions: [] };

type Notice = { kind: "ok" | "error"; text: string } | null;

export default function PresetEditor() {
  const router = useRouter();
  const nameParam = useSearchParams().get("name"); // null: a new preset
  const isNew = nameParam === null;
  const { reachable } = useJarvis();

  const [types, setTypes] = useState<ActionType[]>([]);
  const [saved, setSaved] = useState<PresetData | null>(null);
  const [draft, setDraft] = useState<PresetData | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing" | "failed">("loading");
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [warnings, setWarnings] = useState<PhraseWarning[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getActionTypes(), getPresets()])
      .then(([t, p]) => {
        if (cancelled) return;
        setTypes(t.types);
        const found = nameParam === null ? EMPTY : p.presets.find((x) => x.name === nameParam);
        if (!found) return setStatus("missing");
        setSaved(nameParam === null ? null : found);
        setDraft(structuredClone(found));
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("failed");
      });
    return () => {
      cancelled = true;
    };
  }, [nameParam]);

  const body = useMemo(
    () => (draft ? { phrases: draft.phrases, reply: draft.reply, actions: draft.actions.map((a) => cleanAction(a, types)) } : null),
    [draft, types],
  );
  const dirty = useMemo(() => {
    if (!body) return false;
    if (!saved) return true;
    return JSON.stringify(body) !== JSON.stringify({ phrases: saved.phrases, reply: saved.reply, actions: saved.actions.map((a) => cleanAction(a, types)) });
  }, [body, saved, types]);

  const edit = useCallback((change: Partial<PresetData>, structural = false) => {
    setDraft((d) => (d ? { ...d, ...change } : d));
    setNotice(null);
    if (structural) setErrors([]); // step numbers moved: old messages would point at the wrong step
  }, []);

  const save = async (): Promise<boolean> => {
    if (!draft || !body) return false;
    setBusy(true);
    setNotice(null);
    try {
      const result = isNew ? await createPreset({ name: draft.name, ...body }) : await replacePreset(draft.name, body);
      setErrors([]);
      setWarnings(result.warnings);
      setSaved(structuredClone({ ...draft, ...body }));
      setNotice({ kind: "ok", text: "บันทึกแล้ว Jarvis ใช้ได้ทันที ไม่ต้องรีสตาร์ท" });
      if (isNew) router.replace(`/presets/edit/?name=${encodeURIComponent(draft.name)}`);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) {
        setErrors(e.fields);
        setNotice({ kind: "error", text: "บันทึกไม่ได้ ตรวจรายการที่ขึ้นสีแดง" });
      } else {
        setNotice({ kind: "error", text: e instanceof ApiError && e.status === 409 ? "มี preset ชื่อนี้อยู่แล้ว" : "บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง" });
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    if (!draft || isNew) return;
    if (dirty) {
      if (!window.confirm("มีการแก้ไขที่ยังไม่ได้บันทึก\nทดสอบจะรันเวอร์ชันที่บันทึกไว้ บันทึกก่อนทดสอบไหม?")) return;
      if (!(await save())) return;
    }
    setBusy(true);
    try {
      await testPreset(draft.name);
      setNotice({ kind: "ok", text: "สั่งรันแล้ว" });
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof ApiError && e.status === 409 ? "Jarvis กำลังทำงานอื่นอยู่ ลองใหม่อีกครั้ง" : "สั่งรันไม่สำเร็จ",
      });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!draft || isNew) return;
    if (!window.confirm(`ลบ preset "${draft.name}" ใช่ไหม?\nลบแล้วกู้คืนไม่ได้`)) return;
    setBusy(true);
    try {
      await deletePreset(draft.name);
      router.push("/presets/");
    } catch (e) {
      setNotice({
        kind: "error",
        text: e instanceof ApiError && e.status === 409 ? thaiError("at least one preset must remain") : "ลบไม่สำเร็จ",
      });
      setBusy(false);
    }
  };

  if (reachable === false || status === "failed") {
    return (
      <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center text-red-200">
        Jarvis ไม่ได้เปิดอยู่
      </p>
    );
  }
  if (status === "loading") return <p className="text-slate-500">กำลังโหลด…</p>;
  if (status === "missing" || !draft) {
    return (
      <p className="text-slate-400">
        ไม่พบ preset นี้ <Link href="/presets/" className="text-sky-400 hover:underline">กลับไปรายการ</Link>
      </p>
    );
  }

  const errorsFor = (field: string) => messagesFor(errors, field);
  const nameErrors = errorsFor("name");
  const nameInvalid = isNew && draft.name !== "" && !NAME_RE.test(draft.name);
  const move = (i: number, delta: -1 | 1) => {
    const actions = [...draft.actions];
    [actions[i], actions[i + delta]] = [actions[i + delta], actions[i]];
    edit({ actions }, true);
  };
  const inputClass = (bad: boolean) =>
    `w-full rounded-lg border bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500 ${bad ? "border-red-500" : "border-slate-700"}`;
  const button = "rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link href="/presets/" className="text-sm text-sky-400 hover:underline">
          ← Presets
        </Link>
        <h1 className="text-xl font-semibold">{isNew ? "เพิ่ม preset" : draft.name}</h1>
      </div>

      {notice && (
        <p role={notice.kind === "error" ? "alert" : "status"} className={`rounded-lg border p-3 text-sm ${notice.kind === "ok" ? "border-emerald-800 bg-emerald-950/50 text-emerald-200" : "border-red-900 bg-red-950/50 text-red-200"}`}>
          {notice.text}
        </p>
      )}
      {notice?.kind === "error" && errors.length > 0 && (
        <ul className="list-disc space-y-1 pl-6 text-sm text-red-300">
          {errors.map((e, i) => (
            <li key={i}>
              {describeField(e.field)}: {thaiError(e.message)}
            </li>
          ))}
        </ul>
      )}
      {warnings.some((w) => w.kind === "unmatchable") && (
        <div role="status" className="rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-200">
          <p className="font-medium">บันทึกแล้ว แต่มีวลีที่ Jarvis จะไม่จับคู่ (พูดแล้วไม่ทำงาน ควรลบหรือแก้):</p>
          <ul className="mt-1 list-disc pl-6">
            {warnings.filter((w) => w.kind === "unmatchable").map((w, i) => (
              <li key={i}>{thaiError(w.message ?? "")}</li>
            ))}
          </ul>
        </div>
      )}
      {warnings.some((w) => w.kind === "similar") && (
        <div role="status" className="rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-200">
          <p className="font-medium">บันทึกแล้ว แต่มีวลีที่คล้ายกับ preset อื่นมาก (อาจสลับกันตอนพูด):</p>
          <ul className="mt-1 list-disc pl-6">
            {warnings.filter((w) => w.kind === "similar").map((w, i) => (
              <li key={i}>
                &quot;{w.phrase}&quot; คล้ายกับ &quot;{w.similar_to}&quot; ใน {w.preset} ({w.score}%)
              </li>
            ))}
          </ul>
        </div>
      )}

      {isNew && (
        <div>
          <label htmlFor="preset-name" className="mb-1 block text-sm text-slate-300">
            ชื่อ preset
          </label>
          <input
            id="preset-name"
            value={draft.name}
            onChange={(e) => edit({ name: e.target.value })}
            spellCheck={false}
            aria-invalid={nameInvalid || nameErrors.length > 0}
            aria-describedby="preset-name-hint"
            className={`${inputClass(nameInvalid || nameErrors.length > 0)} font-mono sm:w-72`}
          />
          <p id="preset-name-hint" className={`mt-1 text-xs ${nameInvalid ? "text-red-400" : "text-slate-500"}`}>
            a-z, 0-9 และ - เท่านั้น ไม่เกิน 32 ตัว เช่น open-notes {nameErrors.join(" · ")}
          </p>
        </div>
      )}

      <div>
        <TagInput
          id="phrases"
          label="วลีที่พูด (พิมพ์แล้วกด Enter หรือ ,)"
          value={draft.phrases}
          onChange={(phrases) => edit({ phrases })}
          commaAdds
          invalid={errorsFor("phrases").length > 0}
          describedBy="phrases-err"
          placeholder="เช่น เปิดโหมดเกม"
        />
        {errorsFor("phrases").length > 0 && (
          <p id="phrases-err" role="alert" className="mt-1 text-sm text-red-400">
            {errorsFor("phrases").join(" · ")}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="reply" className="mb-1 block text-sm text-slate-300">
          คำตอบที่ Jarvis พูด
        </label>
        <input id="reply" value={draft.reply} onChange={(e) => edit({ reply: e.target.value })} className={inputClass(errorsFor("reply").length > 0)} aria-describedby="reply-err" />
        {errorsFor("reply").length > 0 && (
          <p id="reply-err" role="alert" className="mt-1 text-sm text-red-400">
            {errorsFor("reply").join(" · ")}
          </p>
        )}
      </div>

      <section aria-labelledby="steps-title">
        <h2 id="steps-title" className="mb-3 text-sm font-semibold text-slate-400">
          ขั้นตอน ({draft.actions.length})
        </h2>
        {errorsFor("actions").length > 0 && <p role="alert" className="mb-2 text-sm text-red-400">{errorsFor("actions").join(" · ")}</p>}
        <ol className="flex flex-col gap-3">
          {draft.actions.map((action: ActionData, i) => (
            <ActionEditor
              key={i}
              index={i}
              action={action}
              types={types}
              errorsFor={errorsFor}
              first={i === 0}
              last={i === draft.actions.length - 1}
              onChange={(a) => edit({ actions: draft.actions.map((x, j) => (j === i ? a : x)) }, a.type !== action.type)}
              onMove={(delta) => move(i, delta)}
              onDelete={() => edit({ actions: draft.actions.filter((_, j) => j !== i) }, true)}
            />
          ))}
        </ol>
        <div className="mt-3 flex flex-wrap gap-2">
          {types.map((t) => (
            <button
              key={t.type}
              type="button"
              onClick={() => edit({ actions: [...draft.actions, blankAction(t)] })}
              className="rounded-lg border border-dashed border-slate-600 px-3 py-2 text-sm text-slate-300 hover:border-sky-500 hover:text-sky-300"
            >
              + {t.label}
            </button>
          ))}
        </div>
      </section>

      <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center gap-3 border-t border-slate-800 bg-slate-950/95 px-4 py-3">
        <button type="button" onClick={() => void save()} disabled={busy || (isNew ? !NAME_RE.test(draft.name) : !dirty)} className={`${button} bg-emerald-600 text-white hover:bg-emerald-500`}>
          บันทึก
        </button>
        <button type="button" onClick={() => void runTest()} disabled={busy || isNew} title={isNew ? "บันทึกก่อนจึงทดสอบได้" : undefined} className={`${button} border border-slate-600 text-slate-200 hover:bg-slate-800`}>
          ทดสอบ
        </button>
        <span className="flex-1" />
        {!isNew && (
          <button type="button" onClick={() => void remove()} disabled={busy} className={`${button} border border-red-900 text-red-300 hover:bg-red-950`}>
            ลบ
          </button>
        )}
        {dirty && !isNew && <span className="text-xs text-amber-400">ยังไม่ได้บันทึก</span>}
      </div>
    </div>
  );
}
