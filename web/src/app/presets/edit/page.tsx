import { Suspense } from "react";
import PresetEditor from "@/components/PresetEditor";

// useSearchParams needs a Suspense boundary in a static export.
export default function Page() {
  return (
    <Suspense fallback={<p className="text-slate-500">กำลังโหลด…</p>}>
      <PresetEditor />
    </Suspense>
  );
}
