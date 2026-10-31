"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  captureHotkey,
  getSettings,
  micTest,
  putSettings,
  type FieldError,
  type MicLevels,
  type SettingsData,
} from "@/lib/api";
import { messagesFor, thaiError } from "@/lib/errors";
import { useJarvis } from "@/lib/jarvis";

const CAPTURE_SECONDS = 10;
const METER_FULL_SCALE = 0.5; // a level of 0.5 fills the meter: speech is far below full scale

const inputClass = (bad: boolean) =>
  `w-full rounded-lg border bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500 sm:w-48 ${bad ? "border-red-500" : "border-slate-700"}`;

function Toggle({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label htmlFor={id} className="text-sm text-slate-300">
        {label}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400 ${checked ? "bg-emerald-600" : "bg-slate-600"}`}
      >
        <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${checked ? "left-6" : "left-1"}`} />
        <span className="sr-only">{checked ? "เปิด" : "ปิด"}</span>
      </button>
    </div>
  );
}

function NumberField(props: {
  id: string;
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  errors: string[];
  onChange: (v: number) => void;
}) {
  const { id, label, hint, value, min, max, step, errors, onChange } = props;
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-slate-300">
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        aria-invalid={errors.length > 0}
        aria-describedby={`${id}-hint`}
        className={inputClass(errors.length > 0)}
      />
      <p id={`${id}-hint`} className={`mt-1 text-xs ${errors.length ? "text-red-400" : "text-slate-500"}`}>
        {errors.length ? errors.join(" · ") : hint}
      </p>
    </div>
  );
}

const percent = (v: number) => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`;

function Meter({ levels }: { levels: MicLevels }) {
  const width = (v: number) => `${Math.min(1, v / METER_FULL_SCALE) * 100}%`;
  const loud = levels.level > levels.threshold;
  return (
    <div className="mt-3">
      <div className="relative h-5 overflow-hidden rounded-full bg-slate-800" role="img" aria-label={`เสียงดังสุด ${percent(levels.level)} เกณฑ์ตรวจจับ ${percent(levels.threshold)}`}>
        <div className={`h-full ${loud ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: width(levels.level) }} />
        <div className="absolute top-0 h-full w-0.5 bg-sky-300" style={{ left: width(levels.threshold) }} />
      </div>
      <p className="mt-1 text-xs text-slate-500">แถบ = เสียงดังสุด · เส้นฟ้า = เกณฑ์ที่ถือว่าเป็นเสียงพูด</p>
    </div>
  );
}

export default function SettingsView() {
  const { data, reachable } = useJarvis();
  const [saved, setSaved] = useState<SettingsData | null>(null);
  const [form, setForm] = useState<SettingsData | null>(null);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  // hotkey capture
  const [capturing, setCapturing] = useState(false);
  const [left, setLeft] = useState(CAPTURE_SECONDS);
  const [captureMsg, setCaptureMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // mic test
  const [testing, setTesting] = useState(false);
  const [levels, setLevels] = useState<MicLevels | null>(null);
  const [micError, setMicError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((s) => {
        if (cancelled) return;
        setSaved(s);
        setForm(s);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => void (timer.current && clearInterval(timer.current)), []);

  const changes = useMemo(() => {
    if (!form || !saved) return {};
    const diff: Partial<SettingsData> = {};
    for (const k of Object.keys(form) as (keyof SettingsData)[]) {
      if (form[k] !== saved[k]) Object.assign(diff, { [k]: form[k] });
    }
    return diff;
  }, [form, saved]);
  const dirty = Object.keys(changes).length > 0;

  if (reachable === false || failed) {
    return (
      <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center text-red-200">
        Jarvis ไม่ได้เปิดอยู่
      </p>
    );
  }
  if (!form || !saved) return <p className="text-slate-500">กำลังโหลด…</p>;

  const set = <K extends keyof SettingsData>(key: K, value: SettingsData[K]) => {
    setForm({ ...form, [key]: value });
    setNotice(null);
    setErrors((prev) => prev.filter((e) => e.field !== key)); // the message was about the old value
  };
  const errorsFor = (name: string) => messagesFor(errors, name);

  const save = async () => {
    setBusy(true);
    setNotice(null);
    setCaptureMsg(null);
    try {
      const next = await putSettings(changes);
      setSaved(next);
      setForm(next);
      setErrors([]);
      setNotice({ ok: true, text: "บันทึกแล้ว ใช้ได้ทันที ไม่ต้องรีสตาร์ท" });
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) {
        setErrors(e.fields);
        setNotice({ ok: false, text: "บันทึกไม่ได้ ตรวจรายการที่ขึ้นสีแดง" });
      } else {
        setNotice({ ok: false, text: "บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง" });
      }
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    setCapturing(true);
    setCaptureMsg(null);
    setLeft(CAPTURE_SECONDS);
    timer.current = setInterval(() => setLeft((n) => Math.max(0, n - 1)), 1000);
    try {
      const r = await captureHotkey();
      if (r.reason === "timeout") {
        setCaptureMsg({ ok: false, text: "หมดเวลา ไม่มีการกดปุ่ม" });
      } else if (r.ok && r.hotkey) {
        set("hotkey", r.hotkey);
        setCaptureMsg({ ok: true, text: `ได้ปุ่ม ${r.hotkey} กด "บันทึก" เพื่อใช้งาน` });
      } else {
        setCaptureMsg({ ok: false, text: `ใช้ ${r.hotkey} ไม่ได้: ${thaiError(r.reason ?? "")}` });
      }
    } catch (e) {
      setCaptureMsg({
        ok: false,
        text: e instanceof ApiError && e.status === 409 ? "กำลังตั้งปุ่มอยู่แล้ว" : "ตั้งปุ่มไม่สำเร็จ ลองใหม่อีกครั้ง",
      });
    } finally {
      if (timer.current) clearInterval(timer.current);
      setCapturing(false);
    }
  };

  const runMicTest = async () => {
    setTesting(true);
    setLevels(null);
    setMicError(null);
    try {
      setLevels(await micTest());
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setMicError(
        code === "off" ? "เปิดสวิตช์ Jarvis ก่อน"
        : code === "busy" ? "Jarvis กำลังทำงานอื่นอยู่ ลองใหม่อีกครั้ง"
        : code === "no_microphone" ? "ไม่พบไมค์ ต่อไมค์และตั้งเป็นอุปกรณ์เสียงเข้าเริ่มต้นของ Windows"
        : "ทดสอบไมค์ไม่สำเร็จ",
      );
    } finally {
      setTesting(false);
    }
  };

  const section = "rounded-xl border border-slate-800 bg-slate-900/60 p-4";
  const micBlocked = !data || data.state !== "idle";
  const verdict: ReactNode = levels
    ? levels.detects_speech
      ? "✓ ตรวจพบเสียงพูด: การหยุดอัตโนมัติน่าจะทำงานได้ดีในห้องนี้"
      : levels.level > levels.threshold
        ? "เสียงดังพอแต่สั้นเกินไป: ต้องพูดต่อเนื่องอย่างน้อยประมาณ 0.1 วินาที"
        : "ไม่ได้ยินเสียงพูดเหนือเสียงรบกวน: พูดดังขึ้น ขยับเข้าใกล้ไมค์ หรือเช็กว่าเลือกไมค์ถูกตัวใน Windows"
    : null;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">ตั้งค่า</h1>

      {notice && (
        <p role={notice.ok ? "status" : "alert"} className={`rounded-lg border p-3 text-sm ${notice.ok ? "border-emerald-800 bg-emerald-950/50 text-emerald-200" : "border-red-900 bg-red-950/50 text-red-200"}`}>
          {notice.text}
        </p>
      )}

      <section className={section} aria-labelledby="hotkey-title">
        <h2 id="hotkey-title" className="mb-3 text-sm font-semibold text-slate-400">
          ปุ่มลัด
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <kbd className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-slate-100">{form.hotkey}</kbd>
          {form.hotkey !== saved.hotkey && <span className="text-xs text-amber-400">ยังไม่ได้บันทึก</span>}
          <button type="button" onClick={() => void capture()} disabled={capturing} className="rounded-lg border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800 disabled:opacity-50">
            ตั้งปุ่มใหม่
          </button>
        </div>
        {capturing && (
          <p role="status" className="mt-3 text-sm text-sky-300">
            กดปุ่มที่ต้องการภายใน {left} วินาที…
          </p>
        )}
        {captureMsg && (
          <p role={captureMsg.ok ? "status" : "alert"} className={`mt-3 text-sm ${captureMsg.ok ? "text-emerald-300" : "text-red-400"}`}>
            {captureMsg.text}
          </p>
        )}
        {errorsFor("hotkey").length > 0 && (
          <p role="alert" className="mt-3 text-sm text-red-400">
            {errorsFor("hotkey").join(" · ")}
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          ปุ่มตัวอักษร ตัวเลข และปุ่มพิมพ์ (space, enter, tab, backspace, esc, shift) ใช้เดี่ยว ๆ ไม่ได้ ใช้คู่กับ Ctrl/Alt ได้ เช่น ctrl+alt+j แต่ไม่รวมคีย์ลัดระบบ (ctrl+c, ctrl+v, alt+tab ฯลฯ)
        </p>
      </section>

      <section className={`${section} flex flex-col gap-4`} aria-labelledby="listen-title">
        <h2 id="listen-title" className="text-sm font-semibold text-slate-400">
          การฟัง
        </h2>
        <Toggle id="armed-on-start" label="เปิดให้ฟังทันทีเมื่อเริ่ม Jarvis" checked={form.armed_on_start} onChange={(v) => set("armed_on_start", v)} />
        <Toggle id="beep" label="เสียงบี๊บตอนเริ่ม/หยุดฟัง" checked={form.beep} onChange={(v) => set("beep", v)} />
        <NumberField id="silence-ms" label="หยุดฟังหลังเงียบ (มิลลิวินาที)" hint="300–5000 · ค่าเริ่มต้น 1000" value={form.silence_ms} min={300} max={5000} step={100} errors={errorsFor("silence_ms")} onChange={(v) => set("silence_ms", v)} />
        <NumberField id="max-seconds" label="ฟังนานสุด (วินาที)" hint="3–60 · ค่าเริ่มต้น 15" value={form.max_seconds} min={3} max={60} step={1} errors={errorsFor("max_seconds")} onChange={(v) => set("max_seconds", v)} />
        <NumberField id="match-threshold" label="ความมั่นใจขั้นต่ำในการจับคู่คำสั่ง" hint="50–100 · ต่ำกว่านี้ Jarvis จะไม่ทำอะไร ค่าเริ่มต้น 70" value={form.match_threshold} min={50} max={100} step={1} errors={errorsFor("match_threshold")} onChange={(v) => set("match_threshold", v)} />
      </section>

      <div className="flex items-center gap-3">
        <button type="button" onClick={() => void save()} disabled={busy || !dirty || Object.values(form).some((v) => typeof v === "number" && Number.isNaN(v))} className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40">
          บันทึก
        </button>
        {dirty && <span className="text-xs text-amber-400">ยังไม่ได้บันทึก</span>}
      </div>

      <section className={section} aria-labelledby="mic-title">
        <h2 id="mic-title" className="mb-2 text-sm font-semibold text-slate-400">
          ทดสอบไมค์
        </h2>
        <p className="mb-3 text-sm text-slate-400">กดแล้วเงียบประมาณครึ่งวินาที จากนั้นพูดประโยคสั้น ๆ (อัด 3 วินาที ไม่เก็บเสียงไว้)</p>
        <button type="button" onClick={() => void runMicTest()} disabled={testing || micBlocked} className="rounded-lg border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">
          {testing ? "กำลังฟัง… พูดได้เลย" : "ทดสอบไมค์"}
        </button>
        {micBlocked && !testing && <p className="mt-2 text-xs text-slate-500">ใช้ได้เมื่อ Jarvis เปิดอยู่และว่าง</p>}
        {micError && (
          <p role="alert" className="mt-3 text-sm text-red-400">
            {micError}
          </p>
        )}
        {levels && (
          <div role="status" className="mt-3">
            <p className={`text-sm ${levels.detects_speech ? "text-emerald-300" : "text-amber-300"}`}>{verdict}</p>
            <Meter levels={levels} />
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-500">เสียงดังสุด</dt>
              <dd>{percent(levels.level)}</dd>
              <dt className="text-slate-500">เสียงรบกวนในห้อง</dt>
              <dd>{percent(levels.noise)}</dd>
              <dt className="text-slate-500">เกณฑ์ตรวจจับเสียงพูด</dt>
              <dd>{percent(levels.threshold)}</dd>
            </dl>
          </div>
        )}
      </section>
    </div>
  );
}
