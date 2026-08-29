"use client";

import { ms } from "@/lib/format";
import { Empty, Spinner, cx } from "@/components/ui";
import type { Investigation } from "@/lib/types";

export function InvestigationSteps({ investigation }: { investigation: Investigation | null }) {
  if (!investigation) return <Empty>No investigation yet.</Empty>;
  const inv = investigation;
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-fg-muted">
        <span className={cx("font-semibold", inv.status === "COMPLETED" ? "text-ok" : inv.status === "FAILED" ? "text-crit" : "text-accent")}>{inv.status}</span>
        <span>attempt {inv.attempt} · {inv.trigger}</span>
        <span>· provider <span className="mono text-fg">{inv.llm_provider}{inv.llm_model ? `/${inv.llm_model}` : ""}</span></span>
        {inv.duration_ms !== null && <span>· {ms(inv.duration_ms)} total, {ms(inv.llm_ms)} model ({inv.llm_calls} calls)</span>}
      </div>
      <ol className="space-y-1">
        {inv.steps.map((s) => (
          <li key={s.name} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-panel-2/60" title={s.error ?? JSON.stringify(s.output)}>
            <span className="w-4 text-center">
              {s.status === "COMPLETED" ? <span className="text-ok">✓</span> : s.status === "RUNNING" ? <Spinner /> : s.status === "FAILED" ? <span className="text-crit">✗</span> : s.status === "SKIPPED" ? <span className="text-fg-dim">–</span> : <span className="text-fg-dim">○</span>}
            </span>
            <span className={cx("flex-1", s.status === "PENDING" && "text-fg-dim")}>{s.label}</span>
            {s.attempts > 1 && <span className="rounded bg-warn/15 px-1 text-[10px] text-warn">retry ×{s.attempts - 1}</span>}
            <span className="mono text-[11px] text-fg-muted">{s.duration_ms !== null ? ms(s.duration_ms) : ""}</span>
          </li>
        ))}
      </ol>
      {inv.error && <div className="mt-2 rounded-md border border-crit/30 bg-crit/10 p-2 text-xs text-crit">{inv.error}</div>}
    </div>
  );
}
