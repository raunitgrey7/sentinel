"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { usePoll, useRequireAuth } from "@/lib/hooks";
import { ago, confidenceTone, dateTime, duration, pct, SEVERITY_TONE, STATUS_TONE, titleCase } from "@/lib/format";
import { Badge, Button, Empty, Panel, Skeleton, Table, cx } from "@/components/ui";

const FILTERS = [
  { id: "open", label: "Open" },
  { id: "all", label: "All" },
  { id: "RESOLVED", label: "Resolved" },
  { id: "HUMAN_REVIEW", label: "Needs review" },
];

export default function IncidentsPage() {
  const s = useRequireAuth();
  const enabled = s.ready && !!s.token;
  const [filter, setFilter] = useState("open");
  const [offset, setOffset] = useState(0);
  const limit = 25;
  const page = usePoll(
    () => api.incidents({ project: "demo-shop", open_only: filter === "open", status: filter !== "open" && filter !== "all" ? filter : undefined, limit, offset }),
    5000,
    [filter, offset],
    enabled,
  );
  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Incidents</h1>
          <p className="text-xs text-fg-muted">{page.data ? `${page.data.total} matching` : "…"}</p>
        </div>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <Button key={f.id} variant={filter === f.id ? "primary" : "ghost"} onClick={() => { setFilter(f.id); setOffset(0); }}>
              {f.label}
            </Button>
          ))}
        </div>
      </header>
      <Panel padded={false}>
        {!page.data ? (
          <div className="space-y-2 p-4"><Skeleton className="h-8" /><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
        ) : page.data.items.length === 0 ? (
          <div className="p-4"><Empty>Nothing here.</Empty></div>
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Incident</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Primary / blast radius</th>
                <th>Root cause</th>
                <th>Confidence</th>
                <th>Detected</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {page.data.items.map((i) => (
                <tr key={i.id}>
                  <td>
                    <Link href={`/incidents/${i.id}`} className="block">
                      <span className="mono text-xs text-fg-muted">{i.key}</span>
                      <div className="font-medium">{i.title}</div>
                    </Link>
                  </td>
                  <td><Badge tone={SEVERITY_TONE[i.severity] ?? "muted"}>{i.severity}</Badge></td>
                  <td><Badge tone={STATUS_TONE[i.status] ?? "muted"} dot>{i.status.replace(/_/g, " ")}</Badge></td>
                  <td>
                    <div className="text-sm">{i.primary_service}</div>
                    <div className="text-[11px] text-fg-muted">{i.affected_services.filter((x) => x !== i.primary_service).join(", ") || "—"}</div>
                  </td>
                  <td className="text-sm">{i.root_cause_category ? titleCase(i.root_cause_category) : <span className="text-fg-dim">—</span>}</td>
                  <td className={cx("mono", `text-${confidenceTone(i.confidence)}`)}>{i.confidence !== null ? pct(i.confidence) : "—"}</td>
                  <td className="text-xs text-fg-muted" title={dateTime(i.detected_at)}>{ago(i.detected_at)}</td>
                  <td className="mono text-xs text-fg-muted">{duration(i.started_at, i.resolved_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {page.data && page.data.total > limit && (
          <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-fg-muted">
            <span>{offset + 1}–{Math.min(offset + limit, page.data.total)} of {page.data.total}</span>
            <div className="flex gap-1">
              <Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>← prev</Button>
              <Button variant="ghost" disabled={offset + limit >= page.data.total} onClick={() => setOffset(offset + limit)}>next →</Button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
