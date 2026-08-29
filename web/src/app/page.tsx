"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { usePoll, useRequireAuth } from "@/lib/hooks";
import { ago, confidenceTone, pct, ms, STATUS_TONE, titleCase } from "@/lib/format";
import { Badge, Dot, Empty, Panel, Skeleton, Sparkline, Stat, cx } from "@/components/ui";
import type { Incident, ServiceHealth } from "@/lib/types";

export default function OverviewPage() {
  const s = useRequireAuth();
  const enabled = s.ready && !!s.token;
  const ov = usePoll(() => api.overview(), 5000, [], enabled);
  const health = usePoll(() => api.health(), 5000, [], enabled);
  const incidents = usePoll(() => api.incidents({ project: "demo-shop", open_only: true, limit: 10 }), 5000, [], enabled);
  const deployments = usePoll(() => api.deployments("demo-shop", 6), 15000, [], enabled);
  const o = ov.data;
  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Overview</h1>
          <p className="text-xs text-fg-muted">Sentinel Demo Shop · production · refreshed {ov.lastUpdated ? ago(new Date(ov.lastUpdated).toISOString()) : "…"}</p>
        </div>
        {o && (
          <div className="flex items-center gap-2 text-sm">
            <Dot tone={o.status === "HEALTHY" ? "ok" : "crit"} pulse={o.status !== "HEALTHY"} />
            <span className="font-semibold">{o.status}</span>
          </div>
        )}
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Active incidents" value={o ? o.open_incidents : "…"} tone={o && o.open_incidents > 0 ? "crit" : "ok"} sub={o ? `${o.active_faults} active fault${o.active_faults === 1 ? "" : "s"}` : undefined} />
        <Stat label="Services" value={o ? o.services : "…"} tone="accent" sub={o ? `${o.healthy_services} healthy` : undefined} />
        <Stat label="Risk" value={o ? o.risk : "…"} tone={o?.risk === "HIGH" ? "crit" : o?.risk === "MEDIUM" ? "warn" : "ok"} />
        <Stat label="Model" value={o ? (o.llm.provider === "none" ? "det." : o.llm.provider) : "…"} tone={o?.llm.circuit?.state === "open" ? "warn" : "info"} sub={o ? (o.llm.provider === "none" ? "deterministic narrator" : o.llm.model) : undefined} />
        <Stat label="Root-cause accuracy" value={o?.latest_evaluation ? pct(o.latest_evaluation.root_cause_accuracy, 1) : "—"} tone="violet" sub={o?.latest_evaluation ? `${o.latest_evaluation.cases} benchmark cases` : "run make eval"} />
        <Stat label="Median investigation" value={o?.latest_evaluation ? ms(o.latest_evaluation.median_investigation_ms) : "—"} tone="violet" sub={o?.latest_evaluation ? `p95 ${ms(o.latest_evaluation.p95_investigation_ms)}` : undefined} />
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Panel title="Active incidents" className="xl:col-span-3" padded={false} action={<Link href="/incidents" className="text-accent hover:underline">all incidents →</Link>}>
          {incidents.loading && !incidents.data ? (
            <div className="space-y-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
          ) : incidents.data && incidents.data.items.length ? (
            <ul className="divide-y divide-border">
              {incidents.data.items.map((i) => <IncidentRow key={i.id} i={i} />)}
            </ul>
          ) : (
            <div className="p-4"><Empty>No active incidents. Break something in the <Link href="/chaos" className="text-accent">Chaos Lab</Link>.</Empty></div>
          )}
        </Panel>
        <Panel title="Recent deployments" className="xl:col-span-2" padded={false}>
          {deployments.data?.length ? (
            <ul className="divide-y divide-border text-xs">
              {deployments.data.map((d) => (
                <li key={d.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{d.service} <span className="mono text-fg-muted">{d.previous_version ?? "?"} → {d.version}</span></span>
                    <span className="text-fg-dim">{ago(d.deployed_at)}</span>
                  </div>
                  <div className="mt-0.5 truncate text-fg-muted">{d.commit_sha ? <span className="mono text-accent/80">{d.commit_sha.slice(0, 8)}</span> : null} {d.commit_message}</div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="p-4"><Empty>No deployments recorded yet.</Empty></div>
          )}
        </Panel>
      </div>

      <Panel title="Service health" padded={false} action={<Link href="/services" className="text-accent hover:underline">topology →</Link>}>
        {health.data ? <HealthGrid rows={health.data} /> : <div className="p-4"><Skeleton className="h-24" /></div>}
      </Panel>
    </div>
  );
}

function IncidentRow({ i }: { i: Incident }) {
  return (
    <li>
      <Link href={`/incidents/${i.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-panel-2/60">
        <Dot tone={i.severity === "CRITICAL" || i.severity === "HIGH" ? "crit" : "warn"} pulse={i.status === "INVESTIGATING"} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="mono text-xs text-fg-muted">{i.key}</span>
            <span className="truncate text-sm font-medium">{i.title}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-fg-muted">
            <Badge tone={STATUS_TONE[i.status] ?? "muted"}>{i.status.replace(/_/g, " ")}</Badge>
            <span>{i.affected_services.length} services · {ago(i.detected_at)}</span>
          </div>
        </div>
        <div className="text-right">
          {i.root_cause_category ? (
            <>
              <div className="text-xs">{titleCase(i.root_cause_category)}</div>
              <div className={cx("mono text-sm font-semibold", `text-${confidenceTone(i.confidence)}`)}>{pct(i.confidence)}</div>
            </>
          ) : (
            <span className="text-xs text-fg-muted">{i.status === "INVESTIGATING" ? "investigating…" : "—"}</span>
          )}
        </div>
      </Link>
    </li>
  );
}

function HealthGrid({ rows }: { rows: ServiceHealth[] }) {
  const svc = rows.filter((r) => r.kind === "service");
  const infra = rows.filter((r) => r.kind !== "service");
  return (
    <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {[...svc, ...infra].map((r) => <HealthCell key={r.name} r={r} />)}
    </div>
  );
}

function HealthCell({ r }: { r: ServiceHealth }) {
  const series = usePoll(() => api.series(r.name, "http_error_rate", 15), 10000, [r.name], r.kind === "service");
  const vals = series.data?.map((p) => p.value) ?? [];
  const tone = !r.healthy ? "crit" : r.availability < 0.99 ? "warn" : "ok";
  return (
    <div className="bg-panel px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Dot tone={tone} />
          <span className="text-sm font-medium">{r.name}</span>
          {r.kind !== "service" && <Badge tone="muted">{r.kind}</Badge>}
        </div>
        <span className={cx("mono text-sm", `text-${tone}`)}>{pct(r.availability, 1)}</span>
      </div>
      {r.kind === "service" ? (
        <div className="mt-2 flex items-end justify-between">
          <div className="text-[11px] text-fg-muted mono">
            err {pct(r.error_rate, 1)} · p95 {ms(r.p95_ms)} · {r.request_rate?.toFixed(1) ?? "—"} rps
          </div>
          <Sparkline values={vals} tone={tone} width={90} height={22} threshold={0.1} />
        </div>
      ) : (
        <div className="mt-2 text-[11px] text-fg-dim">{r.version ?? "managed dependency"}</div>
      )}
    </div>
  );
}
