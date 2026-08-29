"use client";

import { useState } from "react";
import { timeHM } from "@/lib/format";
import { Badge, Empty, cx } from "@/components/ui";
import type { ErrorCluster, Evidence } from "@/lib/types";

const KIND_TONE: Record<string, "ok" | "warn" | "crit" | "info" | "muted" | "accent" | "violet"> = {
  metric: "accent",
  log: "warn",
  trace: "info",
  deployment: "violet",
  config: "violet",
  dependency: "muted",
  historical: "muted",
  alert: "crit",
};

export function EvidenceList({ evidence, highlight, onHighlight }: { evidence: Evidence[]; highlight?: string | null; onHighlight?: (ref: string | null) => void }) {
  const [kind, setKind] = useState<string>("all");
  const [open, setOpen] = useState<string | null>(null);
  const kinds = ["all", ...Array.from(new Set(evidence.map((e) => e.kind)))];
  const rows = evidence.filter((e) => kind === "all" || e.kind === kind);
  if (!evidence.length) return <Empty>No evidence collected yet.</Empty>;
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1">
        {kinds.map((k) => (
          <button key={k} onClick={() => setKind(k)} className={cx("rounded-md px-2 py-1 text-[11px]", kind === k ? "bg-accent-soft text-fg" : "text-fg-muted hover:text-fg")}>
            {k} <span className="mono text-fg-dim">{k === "all" ? evidence.length : evidence.filter((e) => e.kind === k).length}</span>
          </button>
        ))}
      </div>
      <ul className="divide-y divide-border">
        {rows.map((e) => {
          const active = highlight === e.ref;
          const isOpen = open === e.ref;
          return (
            <li key={e.ref} id={`evidence-${e.ref}`} className={cx("px-2 py-2 transition", active && "bg-accent-soft")} onMouseEnter={() => onHighlight?.(e.ref)} onMouseLeave={() => onHighlight?.(null)}>
              <button onClick={() => setOpen(isOpen ? null : e.ref)} className="flex w-full items-start gap-2 text-left">
                <span className="mono mt-0.5 w-8 shrink-0 text-[11px] text-accent">{e.ref}</span>
                <span className={cx("mt-0.5 shrink-0", e.direction === "contradicts" ? "text-warn" : e.direction === "neutral" ? "text-fg-dim" : "text-ok")}>{e.direction === "contradicts" ? "⚠" : e.direction === "neutral" ? "○" : "✓"}</span>
                <span className="min-w-0 flex-1 text-sm">{e.summary}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <Badge tone={KIND_TONE[e.kind] ?? "muted"}>{e.kind}</Badge>
                  <span className="mono text-[11px] text-fg-muted" title="evidence weight">{e.weight.toFixed(2)}</span>
                </span>
              </button>
              {isOpen && (
                <div className="ml-10 mt-2 space-y-1 text-[11px] text-fg-muted">
                  <div>source <span className="mono text-fg">{e.source}</span>{e.service && <> · service <span className="text-fg">{e.service}</span></>}{e.ts_start && <> · {timeHM(e.ts_start)}{e.ts_end ? ` → ${timeHM(e.ts_end)}` : ""}</>}</div>
                  {e.signals.length > 0 && <div className="flex flex-wrap gap-1">signals {e.signals.map((s) => <span key={s} className="mono rounded bg-panel-2 px-1 text-fg">{s}</span>)}</div>}
                  <pre className="scroll-thin max-h-48 overflow-auto rounded bg-bg p-2 mono text-[10px] leading-relaxed text-fg-muted">{JSON.stringify(e.detail, null, 2)}</pre>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ClusterList({ clusters }: { clusters: ErrorCluster[] }) {
  if (!clusters.length) return <Empty>No error clusters.</Empty>;
  return (
    <ul className="divide-y divide-border">
      {clusters.map((c) => (
        <li key={c.id} className="px-2 py-2">
          <div className="flex items-center gap-2 text-xs">
            <Badge tone={c.level === "ERROR" || c.level === "FATAL" ? "crit" : "warn"}>{c.level}</Badge>
            <span className="font-medium">{c.service}</span>
            <span className="mono text-fg-muted">{c.count.toLocaleString()} occurrences</span>
            <span className={cx("mono", c.burst_ratio >= 3 ? "text-crit" : "text-fg-dim")}>{c.baseline_count ? `${c.burst_ratio.toFixed(0)}× baseline` : "new"}</span>
          </div>
          <div className="mt-1 mono text-[11px] text-fg">{c.template}</div>
          <div className="mt-0.5 truncate text-[11px] text-fg-dim">e.g. {c.sample}</div>
        </li>
      ))}
    </ul>
  );
}
