"use client";

import { useState } from "react";

interface Props {
  id: string;
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  /** a comma also adds a tag (phrases). Off for lists whose items may contain commas (args, URLs). */
  commaAdds?: boolean;
  invalid?: boolean;
  describedBy?: string;
  mono?: boolean;
}

/** Type + Enter adds a tag, × removes it, duplicates are ignored. */
export default function TagInput({ id, label, value, onChange, placeholder, commaAdds = false, invalid, describedBy, mono }: Props) {
  const [text, setText] = useState("");

  const commit = (raw: string) => {
    const parts = (commaAdds ? raw.split(",") : [raw]).map((s) => s.trim()).filter(Boolean);
    const next = [...value];
    for (const part of parts) if (!next.includes(part)) next.push(part);
    if (next.length !== value.length) onChange(next);
    setText("");
  };

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-slate-300">
        {label}
      </label>
      <div
        className={`flex flex-wrap items-center gap-2 rounded-lg border bg-slate-950 p-2 focus-within:ring-2 focus-within:ring-sky-500 ${
          invalid ? "border-red-500" : "border-slate-700"
        }`}
      >
        {value.map((tag) => (
          <span key={tag} className={`flex items-center gap-1 rounded-full bg-slate-800 py-1 pr-1 pl-3 text-sm ${mono ? "font-mono" : ""}`}>
            <span className="break-all">{tag}</span>
            <button
              type="button"
              onClick={() => onChange(value.filter((t) => t !== tag))}
              aria-label={`ลบ ${tag}`}
              className="flex h-6 w-6 items-center justify-center rounded-full text-slate-400 hover:bg-slate-700 hover:text-white"
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={id}
          value={text}
          onChange={(e) => (commaAdds && e.target.value.includes(",") ? commit(e.target.value) : setText(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) {
              e.preventDefault();
              commit(text);
            }
          }}
          onBlur={() => commit(text)}
          placeholder={placeholder}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          className={`min-w-40 flex-1 bg-transparent px-1 py-1 text-sm outline-none placeholder:text-slate-600 ${mono ? "font-mono" : ""}`}
        />
      </div>
    </div>
  );
}
