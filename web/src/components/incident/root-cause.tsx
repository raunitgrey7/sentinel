"use client";

import { confidenceTone, pct, titleCase } from "@/lib/format";
import { Badge, Progress, cx } from "@/components/ui";
import type { Evidence, Hypothesis, Incident, Investigation } from "@/lib/types";

export function RootCauseCard({ incident, top, evidence, investigation, onRef }: { incident: Incident; top: Hypothesis | null; evidence: Evidence[]; investigation: Investigation | null; onRef?: (ref: string) => void }) {
  const ev = new Map(evidence.map((e) => [e.ref, e]));
  const tone = confidenceTone(top?.confidence ?? incident.confidence);
  const synthesis = investigation?.summary?.synthesis;
  if (!top) {
    return (
      <section className="panel p-4">
        <div className="panel-title">Root cause</div>
        <div className="mt-2 text-sm text-fg-muted">{incident.status === "INVESTIGATING" || incident.status === "DETECTED" ? "Investigation in progress…" : "No hypothesis has been generated yet."}</div>
      </section>
    );
  }
  return (
    <section className={cx("panel overflow-hidden", tone === "ok" ? "border-ok/40" : tone === "warn" ? "border-warn/40" : "border-crit/40")}>
      <div className="flex flex-wrap items-start justify-between gap-4 p-4">
        <div className="min-w-0 flex-1">
          <div className="panel-title">Probable root cause</div>
          <h2 className="mt-1 text-xl font-semibold">{top.title}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
            <Badge tone="info">{titleCase(top.category)}</Badge>
            {top.culprit_service && <span>culprit <span className="text-fg">{top.culprit_service}</span></span>}
            <span>· {top.verification?.evidence_kinds?.length ?? 0} independent evidence kinds</span>
            <span>· verified: {top.verification?.supported ? <span className="text-ok">yes</span> : <span className="text-crit">no</span>}</span>
          </div>
          {synthesis?.summary && <p className="mt-3 text-sm leading-relaxed text-fg">{synthesis.summary}</p>}
          {top.reasoning && <p className="mt-2 text-sm leading-relaxed text-fg-muted">{top.reasoning}</p>}
        </div>
        <div className="w-44 shrink-0 text-right">
          <div className="panel-title">Confidence</div>
          <div className={cx("mono text-4xl font-semibold", `text-${tone}`)}>{pct(top.confidence)}</div>
          <Progress value={top.confidence} tone={tone} className="mt-2" />
          <div className="mt-1 text-[11px] text-fg-muted">deterministic score {pct(top.score)}{top.verification?.model_confidence !== null && top.verification?.model_confidence !== undefined ? ` · model ${pct(top.verification.model_confidence)}` : ""}</div>
        </div>
      </div>
      <div className="grid gap-px border-t border-border bg-border md:grid-cols-2">
        <div className="bg-panel p-4">
          <div className="panel-title text-ok">Evidence</div>
          <ul className="mt-2 space-y-1.5">
            {top.supporting_evidence.length === 0 && <li className="text-xs text-fg-muted">none cited</li>}
            {top.supporting_evidence.map((r) => (
              <li key={r} className="flex gap-2 text-sm">
                <span className="text-ok">✓</span>
                <button onClick={() => onRef?.(r)} className="text-left hover:underline">
                  <span className="mono mr-1.5 text-[11px] text-accent">{r}</span>
                  {ev.get(r)?.summary ?? "—"}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-panel p-4">
          <div className="panel-title text-warn">Contradicting evidence</div>
          <ul className="mt-2 space-y-1.5">
            {top.contradicting_evidence.length === 0 && <li className="text-xs text-fg-muted">none recorded</li>}
            {top.contradicting_evidence.map((r) => (
              <li key={r} className="flex gap-2 text-sm">
                <span className="text-warn">⚠</span>
                <button onClick={() => onRef?.(r)} className="text-left hover:underline">
                  <span className="mono mr-1.5 text-[11px] text-accent">{r}</span>
                  {ev.get(r)?.summary ?? "—"}
                </button>
              </li>
            ))}
          </ul>
          {(top.verification?.issues?.length ?? 0) > 0 && (
            <div className="mt-3 rounded-md border border-warn/30 bg-warn/10 p-2 text-xs text-warn">
              <div className="font-semibold">Verifier notes</div>
              <ul className="mt-1 list-disc pl-4">{top.verification.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
            </div>
          )}
        </div>
      </div>
      <div className="border-t border-border bg-bg-elev px-4 py-2.5 text-[11px] text-fg-muted">
        <span className="font-semibold text-fg">Confidence caveat.</span> {synthesis?.caveats?.length ? synthesis.caveats.join(" ") : "Correlation with the cited evidence is strong, but causality has not been independently verified. Confidence is capped at 95% and reduced by contradicting evidence, missing evidence kinds and invalid citations."}
        {synthesis?.provider && <span className="ml-1 mono text-fg-dim">· narrated by {synthesis.provider}{synthesis.model ? `/${synthesis.model}` : ""}</span>}
      </div>
    </section>
  );
}
