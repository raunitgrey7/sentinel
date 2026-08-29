"use client";

import { useState } from "react";
import { confidenceTone, pct, titleCase } from "@/lib/format";
import { Badge, Empty, Progress, cx } from "@/components/ui";
import type { Hypothesis } from "@/lib/types";

const BREAKDOWN_LABELS: Record<string, string> = {
  signal_support: "signal support",
  temporal_correlation: "temporal correlation",
  dependency_relevance: "dependency relevance",
  historical_similarity: "historical similarity",
  contradictory_evidence: "contradictory evidence",
};

export function HypothesesList({ hypotheses, onRef }: { hypotheses: Hypothesis[]; onRef?: (ref: string) => void }) {
  const [open, setOpen] = useState<string | null>(hypotheses[0]?.id ?? null);
  if (!hypotheses.length) return <Empty>No hypotheses yet.</Empty>;
  return (
    <ol className="space-y-2">
      {hypotheses.map((h) => {
        const tone = confidenceTone(h.confidence);
        const isOpen = open === h.id;
        return (
          <li key={h.id} className={cx("rounded-md border border-border bg-bg-elev", h.rank === 1 && "border-border-strong")}>
            <button onClick={() => setOpen(isOpen ? null : h.id)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left">
              <span className="mono w-6 text-center text-xs text-fg-muted">#{h.rank}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{h.title}</span>
                  <Badge tone={h.status === "verified" ? "ok" : h.status === "rejected" ? "crit" : "muted"}>{h.status}</Badge>
                  {h.culprit_service && <span className="text-[11px] text-fg-muted">{h.culprit_service}</span>}
                </div>
                <Progress value={h.confidence} tone={tone} className="mt-1.5 max-w-xs" />
              </div>
              <span className={cx("mono text-lg font-semibold", `text-${tone}`)}>{pct(h.confidence)}</span>
            </button>
            {isOpen && (
              <div className="space-y-3 border-t border-border px-3 py-3 text-xs">
                <p className="text-fg-muted">{h.description}</p>
                {h.reasoning && <p className="text-fg">{h.reasoning}</p>}
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <div className="panel-title">Score breakdown</div>
                    <ul className="mt-1 space-y-1">
                      {Object.entries(h.score_breakdown).filter(([k]) => k in BREAKDOWN_LABELS).map(([k, v]) => (
                        <li key={k} className="flex items-center gap-2">
                          <span className="w-40 text-fg-muted">{BREAKDOWN_LABELS[k]}</span>
                          <div className="h-1.5 flex-1 rounded bg-panel-2">
                            <div className={cx("h-full rounded", v < 0 ? "bg-crit" : "bg-accent")} style={{ width: `${Math.min(100, Math.abs(v) * 70)}%` }} />
                          </div>
                          <span className={cx("mono w-12 text-right", v < 0 ? "text-crit" : "text-fg")}>{v >= 0 ? "+" : ""}{v.toFixed(2)}</span>
                        </li>
                      ))}
                      <li className="flex items-center gap-2 border-t border-border pt-1"><span className="w-40 text-fg-muted">raw → score</span><span className="mono">{(h.score_breakdown.raw ?? 0).toFixed(2)} → {h.score.toFixed(2)}</span></li>
                      <li className="flex items-center gap-2"><span className="w-40 text-fg-muted">calibrated confidence</span><span className={cx("mono", `text-${tone}`)}>{h.confidence.toFixed(2)}</span><span className="text-fg-dim">(citations {pct(h.verification?.citation_validity ?? 1)}, penalty −{(h.verification?.contradiction_penalty ?? 0).toFixed(2)}, {h.verification?.evidence_kinds?.length ?? 0} kinds)</span></li>
                    </ul>
                  </div>
                  <div>
                    <div className="panel-title">Citations</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {h.supporting_evidence.map((r) => <button key={r} onClick={() => onRef?.(r)} className="mono rounded border border-ok/30 bg-ok/10 px-1.5 py-0.5 text-ok hover:brightness-125">{r}</button>)}
                      {h.contradicting_evidence.map((r) => <button key={r} onClick={() => onRef?.(r)} className="mono rounded border border-warn/30 bg-warn/10 px-1.5 py-0.5 text-warn hover:brightness-125">{r}</button>)}
                      {!h.supporting_evidence.length && !h.contradicting_evidence.length && <span className="text-fg-dim">none</span>}
                    </div>
                    {h.verification?.issues?.length > 0 && (
                      <ul className="mt-2 list-disc space-y-0.5 pl-4 text-warn">{h.verification.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
                    )}
                    {h.remediation?.length > 0 && (
                      <div className="mt-2">
                        <div className="panel-title">Playbook</div>
                        <ul className="mt-1 space-y-0.5 text-fg-muted">{h.remediation.map((r, k) => <li key={k}>• {r.title} <span className="text-fg-dim">({r.kind}, {r.risk} risk)</span></li>)}</ul>
                      </div>
                    )}
                  </div>
                </div>
                <div className="text-[11px] text-fg-dim">category <span className="mono">{titleCase(h.category)}</span></div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
