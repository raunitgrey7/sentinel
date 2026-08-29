"use client";

import { api } from "@/lib/api";
import { useAsyncAction, useSession } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { Button, Empty, ErrorNote, Spinner } from "@/components/ui";
import type { Postmortem } from "@/lib/types";

export function PostmortemPanel({ incidentId, postmortem, canGenerate, onChange, onRef }: { incidentId: string; postmortem: Postmortem | null; canGenerate: boolean; onChange: () => void; onRef?: (ref: string) => void }) {
  const s = useSession();
  const isEng = ["ENGINEER", "SRE", "ADMIN"].includes(s.user?.role ?? "");
  const { busy, error, run } = useAsyncAction();
  const generate = async () => {
    await run(() => api.generatePostmortem(incidentId));
    onChange();
  };
  const cite = (refs: string[]) => refs.map((r) => <button key={r} onClick={() => onRef?.(r)} className="mono mr-1 rounded bg-accent-soft px-1 text-[10px] text-accent hover:brightness-125">{r}</button>);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[11px] text-fg-muted">{postmortem ? <>v{postmortem.version} · generated {ago(postmortem.generated_at)} by <span className="mono">{postmortem.generated_by}</span> · {postmortem.citations.length} citations</> : "Every claim links back to evidence handles."}</div>
        <div className="flex gap-2">
          {postmortem && <Button onClick={() => { const blob = new Blob([postmortem.content_md], { type: "text/markdown" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `postmortem-${incidentId}.md`; a.click(); URL.revokeObjectURL(url); }}>Download .md</Button>}
          <Button variant="primary" onClick={generate} disabled={busy || !isEng || !canGenerate} title={!canGenerate ? "Available once the investigation has completed" : undefined}>{busy ? <Spinner /> : postmortem ? "Regenerate" : "Generate postmortem"}</Button>
        </div>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {!postmortem ? (
        <Empty>No postmortem yet.</Empty>
      ) : (
        <div className="space-y-4">
          {postmortem.sections.sections.map((sec) => (
            <section key={sec.title}>
              <h3 className="text-sm font-semibold">{sec.title}</h3>
              <div className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-fg">{sec.body}</div>
              {sec.citations.length > 0 && <div className="mt-1">{cite(sec.citations)}</div>}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
