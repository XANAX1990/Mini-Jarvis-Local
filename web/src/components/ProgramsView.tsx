"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  addProgram,
  deleteProgram,
  getPrograms,
  updateProgram,
  type FieldError,
  type ProgramBody,
  type ProgramData,
} from "@/lib/api";
import { messagesFor, thaiError } from "@/lib/errors";
import { useJarvis } from "@/lib/jarvis";
import TagInput from "./TagInput";

const NAME_RE = /^[a-z0-9-]{1,32}$/;
const WAIT_SECONDS = 60; // how long the Yes/No box on the desktop waits for an answer

type Notice = { ok: boolean; text: string } | null;
type Draft = { kind: "exe" | "uri"; path: string; args: string[]; uri: string };

const EMPTY: Draft = { kind: "exe", path: "", args: [], uri: "" };
const toDraft = (p: ProgramData): Draft =>
  p.kind === "exe" ? { kind: "exe", path: p.path, args: p.args, uri: "" } : { kind: "uri", path: "", args: [], uri: p.uri };
const toBody = (d: Draft): ProgramBody => (d.kind === "exe" ? { kind: "exe", path: d.path, args: d.args } : { kind: "uri", uri: d.uri });
const complete = (d: Draft) => (d.kind === "exe" ? d.path.trim() !== "" : d.uri.trim() !== "");

const field = (bad: boolean) =>
  `w-full rounded-lg border bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50 ${bad ? "border-red-500" : "border-slate-700"}`;

/** The kind switch and the fields of one entry: used to add an app and to change one. */
function EntryFields(props: {
  idPrefix: string;
  draft: Draft;
  onChange: (d: Draft) => void;
  disabled: boolean;
  errorsFor: (field: string) => string[];
}) {
  const { idPrefix, draft, onChange, disabled, errorsFor } = props;
  const set = (change: Partial<Draft>) => onChange({ ...draft, ...change });
  return (
    <div className="flex flex-col gap-4">
      <fieldset className="flex flex-wrap gap-4" disabled={disabled}>
        <legend className="mb-1 text-sm text-slate-300">ชนิด</legend>
        {(
          [
            ["exe", "โปรแกรม (.exe)"],
            ["uri", "ลิงก์แอป (เช่น roblox:)"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="flex items-center gap-2 text-sm text-slate-200">
            <input type="radio" name={`${idPrefix}-kind`} checked={draft.kind === value} onChange={() => set({ kind: value })} />
            {label}
          </label>
        ))}
      </fieldset>

      {draft.kind === "exe" ? (
        <>
          <div>
            <label htmlFor={`${idPrefix}-path`} className="mb-1 block text-sm text-slate-300">
              ไฟล์โปรแกรม (.exe)
            </label>
            <input
              id={`${idPrefix}-path`}
              value={draft.path}
              onChange={(e) => set({ path: e.target.value })}
              disabled={disabled}
              spellCheck={false}
              aria-invalid={errorsFor("path").length > 0}
              aria-describedby={`${idPrefix}-path-hint`}
              className={`${field(errorsFor("path").length > 0)} font-mono`}
            />
            <p id={`${idPrefix}-path-hint`} className={`mt-1 text-xs ${errorsFor("path").length ? "text-red-400" : "text-slate-500"}`}>
              {errorsFor("path").length
                ? errorsFor("path").join(" · ")
                : "Shift + คลิกขวาที่ไฟล์ → Copy as path (วางได้เลย ระบบตัดเครื่องหมายคำพูดให้) ต้องเป็น path เต็ม ลงท้าย .exe และมีไฟล์อยู่จริง"}
            </p>
          </div>
          <div>
            <TagInput
              id={`${idPrefix}-args`}
              label="อาร์กิวเมนต์ (พิมพ์แล้วกด Enter ไม่ใส่ก็ได้)"
              value={draft.args}
              onChange={(args) => set({ args })}
              invalid={errorsFor("args").length > 0}
              mono
            />
            {errorsFor("args").length > 0 && (
              <p role="alert" className="mt-1 text-sm text-red-400">
                {errorsFor("args").join(" · ")}
              </p>
            )}
          </div>
        </>
      ) : (
        <div>
          <label htmlFor={`${idPrefix}-uri`} className="mb-1 block text-sm text-slate-300">
            ลิงก์แอป
          </label>
          <input
            id={`${idPrefix}-uri`}
            value={draft.uri}
            onChange={(e) => set({ uri: e.target.value })}
            disabled={disabled}
            spellCheck={false}
            aria-invalid={errorsFor("uri").length > 0}
            aria-describedby={`${idPrefix}-uri-hint`}
            className={`${field(errorsFor("uri").length > 0)} font-mono`}
          />
          <p id={`${idPrefix}-uri-hint`} className={`mt-1 text-xs ${errorsFor("uri").length ? "text-red-400" : "text-slate-500"}`}>
            {errorsFor("uri").length ? errorsFor("uri").join(" · ") : "เก็บลิงก์เต็มตามที่พิมพ์ เช่น roblox: หรือ steam://run/1 (ไม่รับ file: ms-… javascript:)"}
          </p>
        </div>
      )}
    </div>
  );
}

export default function ProgramsView() {
  const { reachable } = useJarvis();
  const [programs, setPrograms] = useState<ProgramData[] | null>(null);
  const [failed, setFailed] = useState(false);

  const [name, setName] = useState("");
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Draft>(EMPTY);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [pending, setPending] = useState<"add" | "change" | null>(null);
  const [left, setLeft] = useState(WAIT_SECONDS);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const reload = useCallback(async () => {
    try {
      setPrograms((await getPrograms()).programs);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    getPrograms()
      .then((r) => !cancelled && setPrograms(r.programs))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => () => void (timer.current && clearInterval(timer.current)), []);

  if (reachable === false || failed) {
    return (
      <p role="alert" className="rounded-xl border border-red-900 bg-red-950/60 p-6 text-center text-red-200">
        Jarvis ไม่ได้เปิดอยู่
      </p>
    );
  }

  const errorsFor = (f: string) => messagesFor(errors, f);
  const nameBad = name !== "" && !NAME_RE.test(name);

  /** Run a request that ends in a Yes/No box on the desktop, and say what happened. True if it went through. */
  const withBox = async (kind: "add" | "change", request: () => Promise<void>): Promise<boolean> => {
    setErrors([]);
    setNotice(null);
    setPending(kind);
    setLeft(WAIT_SECONDS);
    timer.current = setInterval(() => setLeft((n) => Math.max(0, n - 1)), 1000);
    const what = kind === "add" ? "ไม่ได้เพิ่ม" : "ไม่ได้แก้ (ใช้ค่าเดิมต่อ)";
    try {
      await request();
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setNotice({ ok: false, text: e.code === "declined" ? `คุณกด No ที่กล่องยืนยัน: ${what}` : `ไม่ได้ตอบกล่องยืนยันภายใน ${WAIT_SECONDS} วินาที: ${what}` });
      } else if (e instanceof ApiError && e.status === 409 && e.code === "busy") {
        setNotice({ ok: false, text: "มีกล่องยืนยันเปิดอยู่แล้วบนหน้าจอ ตอบกล่องนั้นก่อน แล้วลองใหม่" });
      } else if (e instanceof ApiError && e.status === 404) {
        setNotice({ ok: false, text: "ไม่พบรายการนี้แล้ว" });
        await reload();
      } else if (e instanceof ApiError && e.fields.length) {
        setErrors(e.fields);
        setNotice({ ok: false, text: "ตรวจรายการที่ขึ้นสีแดง" });
      } else {
        setNotice({ ok: false, text: "ไม่สำเร็จ ลองใหม่อีกครั้ง" });
      }
      return false;
    } finally {
      if (timer.current) clearInterval(timer.current);
      setPending(null);
    }
  };

  const submitAdd = async () => {
    const ok = await withBox("add", async () => {
      await addProgram({ name, ...toBody(draft) } as ProgramData);
    });
    if (!ok) return;
    setNotice({ ok: true, text: `เพิ่ม "${name}" แล้ว ใช้ในขั้นตอน "เปิดแอป" ของ preset ได้เลย` });
    setName("");
    setDraft(EMPTY);
    await reload();
  };

  const submitChange = async (programName: string) => {
    let changed = true;
    const ok = await withBox("change", async () => {
      changed = (await updateProgram(programName, toBody(editDraft))).changed;
    });
    if (!ok) return;
    setNotice({
      ok: true,
      text: changed ? `แก้ "${programName}" แล้ว preset ที่ใช้อยู่จะเปิดค่าใหม่นี้` : `"${programName}" ไม่มีอะไรเปลี่ยน`,
    });
    setEditing(null);
    await reload();
  };

  const startEdit = (p: ProgramData) => {
    setEditing(p.name);
    setEditDraft(toDraft(p));
    setErrors([]);
    setNotice(null);
  };

  const remove = async (programName: string) => {
    setNotice(null);
    try {
      await deleteProgram(programName);
      await reload();
    } catch (e) {
      setNotice({
        ok: false,
        text: e instanceof ApiError && e.status === 409 && e.code === "busy"
          ? "มีกล่องยืนยันเปิดอยู่ ตอบกล่องนั้นก่อน"
          : e instanceof ApiError && e.fields.length
            ? `ลบ "${programName}" ไม่ได้: ${thaiError(e.fields[0].message)}`
            : "ลบไม่สำเร็จ",
      });
    }
  };

  const waiting = pending !== null;
  const boxNotice = (verb: string) => (
    <p role="status" className="rounded-lg border border-sky-800 bg-sky-950/50 p-3 text-sm text-sky-200">
      ดูที่หน้าจอ Windows: มีกล่อง <b>&quot;Jarvis: ยืนยันการเปลี่ยนรายการแอป&quot;</b> ขึ้นมา (อยู่บนสุด) กด <b>Yes</b> เฉพาะเมื่อคุณเป็นคนสั่ง{verb}เอง เหลือเวลา {left} วินาที
      ถ้าไม่ตอบ = ไม่เปลี่ยนอะไร (ถ้าเปิดเกมเต็มจออยู่ กล่องอาจถูกบัง ให้สลับออกมาก่อน)
    </p>
  );

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">โปรแกรม</h1>
        <p className="mt-2 text-sm text-slate-400">
          ขั้นตอน &quot;เปิดแอป&quot; ของ preset เปิดได้เฉพาะแอปในรายการนี้ (โปรแกรม .exe พร้อมอาร์กิวเมนต์ที่กำหนดไว้ หรือลิงก์แอปอย่าง roblox:) ถ้าจะเพิ่มหรือแก้
          ต้องกด <b>Yes</b> ที่กล่องยืนยันบนหน้าจอ Windows ด้วย เว็บอย่างเดียวทำเองไม่ได้
        </p>
      </div>

      {notice && (
        <p role={notice.ok ? "status" : "alert"} className={`rounded-lg border p-3 text-sm ${notice.ok ? "border-emerald-800 bg-emerald-950/50 text-emerald-200" : "border-red-900 bg-red-950/50 text-red-200"}`}>
          {notice.text}
        </p>
      )}

      <div aria-labelledby="list-title">
        <h2 id="list-title" className="mb-3 text-sm font-semibold text-slate-400">
          แอปที่อนุญาต ({programs?.length ?? 0})
        </h2>
        {programs === null ? (
          <p className="text-sm text-slate-500">กำลังโหลด…</p>
        ) : programs.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีรายการ เพิ่มด้านล่าง</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {programs.map((p) => (
              <li key={p.name} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-base font-semibold">{p.name}</span>
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">{p.kind === "uri" ? "ลิงก์แอป" : "โปรแกรม"}</span>
                  </div>
                  {editing !== p.name && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => startEdit(p)}
                        disabled={waiting}
                        aria-label={`แก้ไข ${p.name}`}
                        className="rounded-lg border border-slate-600 px-3 py-1 text-xs text-sky-300 hover:bg-slate-800 disabled:opacity-40"
                      >
                        แก้ไข
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(p.name)}
                        disabled={waiting}
                        aria-label={`ลบโปรแกรม ${p.name}`}
                        className="rounded-lg border border-red-900 px-3 py-1 text-xs text-red-300 hover:bg-red-950 disabled:opacity-40"
                      >
                        ลบ
                      </button>
                    </div>
                  )}
                </div>

                {editing === p.name ? (
                  <div className="mt-4 flex flex-col gap-4">
                    <EntryFields idPrefix="edit" draft={editDraft} onChange={setEditDraft} disabled={waiting} errorsFor={errorsFor} />
                    {pending === "change" && boxNotice("แก้")}
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => void submitChange(p.name)}
                        disabled={waiting || !complete(editDraft)}
                        className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {pending === "change" ? "รอการยืนยันบนหน้าจอ…" : "บันทึก (ต้องยืนยันบนหน้าจอ)"}
                      </button>
                      <button type="button" onClick={() => setEditing(null)} disabled={waiting} className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40">
                        ยกเลิก
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="mt-1 font-mono text-xs break-all text-slate-400">{p.kind === "uri" ? p.uri : p.path}</p>
                    {p.kind === "exe" && p.args.length > 0 && (
                      <ul className="mt-2 flex flex-wrap gap-2" aria-label="อาร์กิวเมนต์">
                        {p.args.map((a, i) => (
                          <li key={i} className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs break-all">
                            {a}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4" role="group" aria-labelledby="add-title">
        <h2 id="add-title" className="mb-3 text-sm font-semibold text-slate-400">
          เพิ่มแอป
        </h2>
        <div className="flex flex-col gap-4">
          <div>
            <label htmlFor="program-name" className="mb-1 block text-sm text-slate-300">
              ชื่อ
            </label>
            <input
              id="program-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={waiting}
              spellCheck={false}
              aria-invalid={nameBad || errorsFor("name").length > 0}
              aria-describedby="program-name-hint"
              className={`${field(nameBad || errorsFor("name").length > 0)} font-mono sm:w-72`}
            />
            <p id="program-name-hint" className={`mt-1 text-xs ${nameBad || errorsFor("name").length ? "text-red-400" : "text-slate-500"}`}>
              a-z, 0-9 และ - เท่านั้น ไม่เกิน 32 ตัว เช่น discord {errorsFor("name").join(" · ")}
            </p>
          </div>
          <EntryFields idPrefix="add" draft={draft} onChange={setDraft} disabled={waiting} errorsFor={editing ? () => [] : errorsFor} />
          {pending === "add" && boxNotice("เพิ่ม")}
          <div>
            <button
              type="button"
              onClick={() => void submitAdd()}
              disabled={waiting || !NAME_RE.test(name) || !complete(draft)}
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {pending === "add" ? "รอการยืนยันบนหน้าจอ…" : "เพิ่ม (ต้องยืนยันบนหน้าจอ)"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
