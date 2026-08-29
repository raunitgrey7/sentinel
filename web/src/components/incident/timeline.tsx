"use client";

import { timeHM } from "@/lib/format";
import { Empty, cx } from "@/components/ui";
import type { IncidentEvent } from "@/lib/types";

const KIND: Record<string, { tone: string; glyph: string }> = {
  deployment: { tone: "text-violet", glyph: "⇪" },
  metric: { tone: "text-accent", glyph: "∿" },
  log: { tone: "text-warn", glyph: "≡" },
  alert: { tone: "text-crit", glyph: "⚑" },
  status: { tone: "text-info", glyph: "◆" },
  investigation: { tone: "text-ok", glyph: "◎" },
  action: { tone: "text-violet", glyph: "▶" },
  note: { tone: "text-fg-muted", glyph: "✎" },
};

export function TimelineView({ events, onset }: { events: IncidentEvent[]; onset?: string }) {
  if (!events.length) return <Empty>No timeline yet.</Empty>;
  return (
    <ol className="relative ml-2 border-l border-border pl-5">
      {events.map((e) => {
        const k = KIND[e.kind] ?? KIND.note;
        const isOnset = onset && Math.abs(new Date(e.ts).getTime() - new Date(onset).getTime()) < 1500 && e.kind === "metric";
        return (
          <li key={e.id} className="relative pb-3 last:pb-0">
            <span className={cx("absolute -left-[27px] top-0.5 grid h-4 w-4 place-items-center rounded-full bg-bg text-[10px]", k.tone)}>{k.glyph}</span>
            <div className="flex items-baseline gap-3">
              <span className="mono w-16 shrink-0 text-[11px] text-fg-muted">{timeHM(e.ts)}</span>
              <span className={cx("text-sm", e.kind === "status" && "text-fg-muted")}>{e.message}</span>
              {isOnset && <span className="rounded bg-crit/15 px-1 text-[10px] text-crit">onset</span>}
            </div>
            {e.actor !== "system" && <div className="ml-[76px] text-[10px] text-fg-dim">by {e.actor}</div>}
          </li>
        );
      })}
    </ol>
  );
}
