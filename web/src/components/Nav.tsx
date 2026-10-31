"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useJarvis } from "@/lib/jarvis";
import { STATE_DOT, STATE_NAME } from "@/lib/labels";

const LINKS = [
  { href: "/", label: "หน้าหลัก" },
  { href: "/presets/", label: "Presets" },
  { href: "/programs/", label: "โปรแกรม" },
  { href: "/log/", label: "Log" },
  { href: "/settings/", label: "ตั้งค่า" },
];

export default function Nav() {
  const pathname = usePathname();
  const { data, reachable } = useJarvis();
  const dot = reachable === false ? "border-2 border-red-500" : data ? STATE_DOT[data.state] : "bg-slate-700";
  const title = reachable === false ? "Jarvis ไม่ได้เปิดอยู่" : data ? STATE_NAME[data.state] : "กำลังเชื่อมต่อ";

  return (
    <header className="border-b border-slate-800 bg-slate-950/80">
      <nav className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-1 gap-y-1 px-4 py-2" aria-label="เมนูหลัก">
        <span className="mr-2 flex items-center gap-2 font-semibold text-slate-100">
          <span role="img" aria-label={title} title={title} className={`inline-block h-3 w-3 rounded-full ${dot}`} />
          Jarvis
        </span>
        {LINKS.map(({ href, label }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm ${
                active ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
