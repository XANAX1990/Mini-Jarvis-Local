"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, addProgram, deleteProgram, getPrograms, type FieldError, type ProgramData } from "@/lib/api";
import { messagesFor, thaiError } from "@/lib/errors";
import { useJarvis } from "@/lib/jarvis";
import TagInput from "./TagInput";

const NAME_RE = /^[a-z0-9-]{1,32}$/;
const WAIT_SECONDS = 60; // how long the Yes/No box on the desktop waits for an answer

type Notice = { ok: boolean; text: string } | null;

const field = (bad: boolean) =>
  `w-full rounded-lg border bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50 ${bad ? "border-red-500" : "border-slate-700"}`;

export default function ProgramsView() {
  const { reachable } = useJarvis();
  const [programs, setPrograms] = useState<ProgramData[] | null>(null);
  const [failed, setFailed] = useState(false);

  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [args, setArgs] = useState<string[]>([]);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [pending, setPending] = useState(false);
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

  const submit = async () => {
    setErrors([]);
    setNotice(null);
    setPending(true);
    setLeft(WAIT_SECONDS);
    timer.current = setInterval(() => setLeft((n) => Math.max(0, n - 1)), 1000);
    try {
      await addProgram({ name, path, args });
      setNotice({ ok: true, text: `เพิ่มโปรแกรม "${name}" แล้ว ใช้ในขั้นตอน "เปิดโปรแกรม" ของ preset ได้เลย` });
      setName("");
      setPath("");
      setArgs([]);
      await reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setNotice({
          ok: false,
          text: e.code === "declined" ? "คุณกด No ที่กล่องยืนยัน: ไม่ได้เพิ่มโปรแกรม" : `ไม่ได้ตอบกล่องยืนยันภายใน ${WAIT_SECONDS} วินาที: ไม่ได้เพิ่มโปรแกรม`,
        });
      } else if (e instanceof ApiError && e.status === 409 && e.code === "busy") {
        setNotice({ ok: false, text: "มีกล่องยืนยันเปิดอยู่แล้วบนหน้าจอ ตอบกล่องนั้นก่อน แล้วลองใหม่" });
      } else if (e instanceof ApiError && e.fields.length) {
        setErrors(e.fields);
        setNotice({ ok: false, text: "เพิ่มไม่ได้ ตรวจรายการที่ขึ้นสีแดง" });
      } else {
        setNotice({ ok: false, text: "เพิ่มไม่สำเร็จ ลองใหม่อีกครั้ง" });
      }
    } finally {
      if (timer.current) clearInterval(timer.current);
      setPending(false);
    }
  };

  const remove = async (programName: string) => {
    setNotice(null);
    try {
      await deleteProgram(programName);
      await reload();
    } catch (e) {
      setNotice({
        ok: false,
        text: e instanceof ApiError && e.fields.length ? `ลบ "${programName}" ไม่ได้: ${thaiError(e.fields[0].message)}` : "ลบไม่สำเร็จ",
      });
    }
  };

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">โปรแกรม</h1>
        <p className="mt-2 text-sm text-slate-400">
          ขั้นตอน &quot;เปิดโปรแกรม&quot; ของ preset เปิดได้เฉพาะโปรแกรมในรายการนี้ ถ้าจะเพิ่มโปรแกรมใหม่ ต้องกด <b>Yes</b> ที่กล่องยืนยันบนหน้าจอ Windows ด้วย
          เว็บอย่างเดียวเพิ่มเองไม่ได้
        </p>
      </div>

      {notice && (
        <p role={notice.ok ? "status" : "alert"} className={`rounded-lg border p-3 text-sm ${notice.ok ? "border-emerald-800 bg-emerald-950/50 text-emerald-200" : "border-red-900 bg-red-950/50 text-red-200"}`}>
          {notice.text}
        </p>
      )}

      <div aria-labelledby="list-title">
        <h2 id="list-title" className="mb-3 text-sm font-semibold text-slate-400">
          โปรแกรมที่อนุญาต ({programs?.length ?? 0})
        </h2>
        {programs === null ? (
          <p className="text-sm text-slate-500">กำลังโหลด…</p>
        ) : programs.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีโปรแกรม เพิ่มด้านล่าง</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {programs.map((p) => (
              <li key={p.name} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="flex items-start justify-between gap-3">
                  <span className="font-mono text-base font-semibold">{p.name}</span>
                  <button
                    type="button"
                    onClick={() => void remove(p.name)}
                    aria-label={`ลบโปรแกรม ${p.name}`}
                    className="rounded-lg border border-red-900 px-3 py-1 text-xs text-red-300 hover:bg-red-950"
                  >
                    ลบ
                  </button>
                </div>
                <p className="mt-1 font-mono text-xs break-all text-slate-400">{p.path}</p>
                {p.args.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2" aria-label="อาร์กิวเมนต์">
                    {p.args.map((a, i) => (
                      <li key={i} className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs break-all">
                        {a}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4" role="group" aria-labelledby="add-title">
        <h2 id="add-title" className="mb-3 text-sm font-semibold text-slate-400">
          เพิ่มโปรแกรม
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
              disabled={pending}
              spellCheck={false}
              aria-invalid={nameBad || errorsFor("name").length > 0}
              aria-describedby="program-name-hint"
              className={`${field(nameBad || errorsFor("name").length > 0)} font-mono sm:w-72`}
            />
            <p id="program-name-hint" className={`mt-1 text-xs ${nameBad || errorsFor("name").length ? "text-red-400" : "text-slate-500"}`}>
              a-z, 0-9 และ - เท่านั้น ไม่เกิน 32 ตัว เช่น discord {errorsFor("name").join(" · ")}
            </p>
          </div>
          <div>
            <label htmlFor="program-path" className="mb-1 block text-sm text-slate-300">
              ไฟล์โปรแกรม (.exe)
            </label>
            <input
              id="program-path"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              disabled={pending}
              spellCheck={false}
              aria-invalid={errorsFor("path").length > 0}
              aria-describedby="program-path-hint"
              className={`${field(errorsFor("path").length > 0)} font-mono`}
            />
            <p id="program-path-hint" className={`mt-1 text-xs ${errorsFor("path").length ? "text-red-400" : "text-slate-500"}`}>
              {errorsFor("path").length ? errorsFor("path").join(" · ") : "Shift + คลิกขวาที่ไฟล์ → Copy as path (วางได้เลย ระบบตัดเครื่องหมายคำพูดให้) ต้องเป็น path เต็ม ลงท้าย .exe และมีไฟล์อยู่จริง"}
            </p>
          </div>
          <div>
            <TagInput id="program-args" label="อาร์กิวเมนต์ (พิมพ์แล้วกด Enter ไม่ใส่ก็ได้)" value={args} onChange={setArgs} invalid={errorsFor("args").length > 0} mono />
            {errorsFor("args").length > 0 && (
              <p role="alert" className="mt-1 text-sm text-red-400">
                {errorsFor("args").join(" · ")}
              </p>
            )}
          </div>

          {pending && (
            <p role="status" className="rounded-lg border border-sky-800 bg-sky-950/50 p-3 text-sm text-sky-200">
              ดูที่หน้าจอ Windows: มีกล่อง <b>&quot;Jarvis: ยืนยันการเพิ่มโปรแกรม&quot;</b> ขึ้นมา (อยู่บนสุด) กด <b>Yes</b> เฉพาะเมื่อคุณเป็นคนสั่งเพิ่มเอง
              เหลือเวลา {left} วินาที ถ้าไม่ตอบ = ไม่เพิ่ม
            </p>
          )}
          <div>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={pending || !NAME_RE.test(name) || path.trim() === ""}
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {pending ? "รอการยืนยันบนหน้าจอ…" : "เพิ่ม (ต้องยืนยันบนหน้าจอ)"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
