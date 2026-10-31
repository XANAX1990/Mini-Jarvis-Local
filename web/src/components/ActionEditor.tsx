"use client";

import Link from "next/link";
import type { ActionData, ActionField, ActionType, ProgramData } from "@/lib/api";
import TagInput from "./TagInput";

const LABEL: Record<string, string> = {
  "run.path": "โปรแกรม (.exe)",
  "run.args": "อาร์กิวเมนต์ (พิมพ์แล้วกด Enter)",
  "app.name": "แอป (เลือกจากรายการที่อนุญาตไว้)",
  "open.target": "ไฟล์ / โฟลเดอร์",
  "uri.target": "ลิงก์แอป (เช่น discord:)",
  "chrome.urls": "ลิงก์ (พิมพ์แล้วกด Enter)",
  "wait.seconds": "รอ (วินาที)",
  "spending.period": "ช่วงเวลา",
};

const PERIOD_LABEL: Record<string, string> = { today: "วันนี้", week: "อาทิตย์นี้", month: "เดือนนี้" };
const PATH_HINT = "Shift + คลิกขวาที่ไฟล์ → Copy as path (วางได้เลย ระบบตัดเครื่องหมายคำพูดให้)";
const OPEN_HINT = "เปิดได้เฉพาะโฟลเดอร์ และไฟล์ pdf, txt, md, docx, xlsx, pptx, png, jpg, jpeg, gif, mp3, mp4 (ไม่รับ .lnk .url .bat .exe)";

/** A new step of this type with empty fields. */
export function blankAction(type: ActionType, programs: ProgramData[] = []): ActionData {
  const action: ActionData = { type: type.type };
  for (const f of type.fields) {
    action[f.name] =
      f.kind === "text-list" ? [] : f.kind === "number" ? 0 : f.kind === "choice" ? (f.options?.[0] ?? "") : f.kind === "program" ? (programs[0]?.name ?? "") : "";
  }
  return action;
}

/** Only the fields the type declares: what is sent to the API. */
export function cleanAction(action: ActionData, types: ActionType[]): ActionData {
  const type = types.find((t) => t.type === action.type);
  const out: ActionData = { type: action.type };
  for (const f of type?.fields ?? []) {
    const v = action[f.name];
    if (f.kind === "number" && v === "") continue;
    if (v !== undefined) out[f.name] = v;
  }
  return out;
}

/** What the chosen program will start, shown read-only: the path and arguments live in programs.json. */
function ProgramInfo({ programs, chosen }: { programs: ProgramData[]; chosen: string }) {
  const program = programs.find((p) => p.name === chosen);
  if (programs.length === 0) {
    return (
      <p className="mt-1 text-xs text-amber-300">
        ยังไม่มีแอปที่อนุญาต{" "}
        <Link href="/programs/" className="text-sky-400 underline">
          ไปเพิ่มที่หน้า โปรแกรม
        </Link>
      </p>
    );
  }
  if (!program) return null;
  return (
    <p className="mt-1 break-all font-mono text-xs text-slate-500">
      {program.kind === "uri" ? program.uri : program.path}
      {program.kind === "exe" && program.args.length > 0 && ` ${program.args.join(" ")}`}
    </p>
  );
}

interface Props {
  index: number;
  action: ActionData;
  types: ActionType[];
  programs: ProgramData[];
  errorsFor: (field: string) => string[];
  first: boolean;
  last: boolean;
  onChange: (action: ActionData) => void;
  onMove: (delta: -1 | 1) => void;
  onDelete: () => void;
}

export default function ActionEditor({ index, action, types, programs, errorsFor, first, last, onChange, onMove, onDelete }: Props) {
  const type = types.find((t) => t.type === action.type);
  const base = `step-${index}`;
  const stepErrors = errorsFor(`actions.${index}`);

  const setField = (name: string, value: unknown) => onChange({ ...action, [name]: value });

  const renderField = (f: ActionField) => {
    const id = `${base}-${f.name}`;
    const errs = errorsFor(`actions.${index}.${f.name}`);
    const err = errs.length > 0;
    const label = LABEL[`${action.type}.${f.name}`] ?? f.name;
    const errId = `${id}-err`;
    const value = action[f.name];
    let input;
    if (f.kind === "text-list") {
      input = (
        <TagInput
          id={id}
          label={label}
          value={Array.isArray(value) ? (value as string[]) : []}
          onChange={(v) => setField(f.name, v)}
          invalid={err}
          describedBy={err ? errId : undefined}
          mono
        />
      );
    } else {
      const common = `w-full rounded-lg border bg-slate-950 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500 ${err ? "border-red-500" : "border-slate-700"}`;
      input = (
        <div>
          <label htmlFor={id} className="mb-1 block text-sm text-slate-300">
            {label}
          </label>
          {f.kind === "program" ? (
            <select id={id} value={String(value ?? "")} onChange={(e) => setField(f.name, e.target.value)} aria-invalid={err} aria-describedby={err ? errId : undefined} className={common}>
              {!programs.some((p) => p.name === value) && (
                <option value={String(value ?? "")}>{value ? `${String(value)} (ไม่พบในรายการ)` : "— เลือกโปรแกรม —"}</option>
              )}
              {programs.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.kind === "uri" ? `${p.name} (ลิงก์แอป)` : p.name}
                </option>
              ))}
            </select>
          ) : f.kind === "choice" ? (
            <select id={id} value={String(value ?? "")} onChange={(e) => setField(f.name, e.target.value)} className={common}>
              {(f.options ?? []).map((o) => (
                <option key={o} value={o}>
                  {PERIOD_LABEL[o] ?? o}
                </option>
              ))}
            </select>
          ) : f.kind === "number" ? (
            <input
              id={id}
              type="number"
              inputMode="decimal"
              min={f.min}
              max={f.max}
              step="0.5"
              value={typeof value === "number" || value === "" ? value : ""}
              onChange={(e) => setField(f.name, e.target.value === "" ? "" : Number(e.target.value))}
              aria-invalid={err}
              aria-describedby={err ? errId : undefined}
              className={`${common} sm:w-40`}
            />
          ) : (
            <input
              id={id}
              type="text"
              value={String(value ?? "")}
              onChange={(e) => setField(f.name, e.target.value)}
              spellCheck={false}
              aria-invalid={err}
              aria-describedby={err ? errId : undefined}
              className={`${common} ${f.kind === "path" ? "font-mono" : ""}`}
            />
          )}
        </div>
      );
    }
    return (
      <div key={f.name}>
        {input}
        {f.kind === "path" && (
          <p className="mt-1 text-xs text-slate-500">
            {PATH_HINT}
            {action.type === "open" && <span className="mt-0.5 block">{OPEN_HINT}</span>}
          </p>
        )}
        {f.kind === "program" && <ProgramInfo programs={programs} chosen={String(value ?? "")} />}
        {err && (
          <p id={errId} role="alert" className="mt-1 text-sm text-red-400">
            {errs.join(" · ")}
          </p>
        )}
      </div>
    );
  };

  const iconButton =
    "flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-30";

  return (
    <li className={`rounded-xl border bg-slate-900/60 p-4 ${stepErrors.length ? "border-red-500" : "border-slate-800"}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-400">{index + 1}.</span>
        <select
          aria-label={`ชนิดของขั้นตอนที่ ${index + 1}`}
          value={action.type}
          onChange={(e) => {
            const next = types.find((t) => t.type === e.target.value);
            if (next) onChange(blankAction(next, programs));
          }}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
        >
          {types.map((t) => (
            <option key={t.type} value={t.type}>
              {t.label}
            </option>
          ))}
        </select>
        <span className="flex-1" />
        <button type="button" className={iconButton} onClick={() => onMove(-1)} disabled={first} aria-label={`ย้ายขั้นตอนที่ ${index + 1} ขึ้น`}>
          ↑
        </button>
        <button type="button" className={iconButton} onClick={() => onMove(1)} disabled={last} aria-label={`ย้ายขั้นตอนที่ ${index + 1} ลง`}>
          ↓
        </button>
        <button type="button" className={`${iconButton} hover:border-red-500 hover:text-red-400`} onClick={onDelete} aria-label={`ลบขั้นตอนที่ ${index + 1}`}>
          🗑
        </button>
      </div>
      {stepErrors.length > 0 && (
        <p role="alert" className="mb-3 text-sm text-red-400">
          {stepErrors.join(" · ")}
        </p>
      )}
      <div className="flex flex-col gap-3">{type ? type.fields.map(renderField) : <p className="text-sm text-red-400">ไม่รู้จักชนิดขั้นตอนนี้</p>}</div>
    </li>
  );
}
