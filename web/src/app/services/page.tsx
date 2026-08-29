"use client";

import { api } from "@/lib/api";
import { usePoll, useRequireAuth } from "@/lib/hooks";
import { ago, ms, pct } from "@/lib/format";
import { Badge, Dot, Panel, Skeleton, Sparkline, Table, cx } from "@/components/ui";
import { TopologyView } from "@/components/topology";

export default function ServicesPage() {
  const s = useRequireAuth();
  const enabled = s.ready && !!s.token;
  const topo = usePoll(() => api.topology(), 30000, [], enabled);
  const health = usePoll(() => api.health(), 5000, [], enabled);
  const incidents = usePoll(() => api.incidents({ project: "demo-shop", open_only: true, limit: 20 }), 5000, [], enabled);
  const affected = new Set(incidents.data?.items.flatMap((i) => i.affected_services) ?? []);
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Services & topology</h1>
        <p className="text-xs text-fg-muted">Dependency graph registered with Sentinel · calls flow left → right · red = inside an open incident&apos;s blast radius</p>
      </header>
      <Panel title="Topology" padded={false}>
        <div className="p-3">{topo.data ? <TopologyView topology={topo.data} health={health.data ?? []} highlight={[...affected]} /> : <Skeleton className="h-64" />}</div>
      </Panel>
      <Panel title="Health" padded={false}>
        {health.data ? (
          <Table>
            <thead>
              <tr><th>Service</th><th>Kind</th><th>Version</th><th>Availability (15m)</th><th>Error rate</th><th>p95</th><th>Throughput</th><th>Incidents</th><th>Last seen</th><th>Error trend</th></tr>
            </thead>
            <tbody>
              {health.data.map((h) => <Row key={h.name} h={h} />)}
            </tbody>
          </Table>
        ) : (
          <div className="p-4"><Skeleton className="h-40" /></div>
        )}
      </Panel>
    </div>
  );
}

function Row({ h }: { h: import("@/lib/types").ServiceHealth }) {
  const series = usePoll(() => api.series(h.name, "http_error_rate", 20), 10000, [h.name], h.kind === "service");
  const tone = !h.healthy ? "crit" : h.availability < 0.99 ? "warn" : "ok";
  return (
    <tr>
      <td><div className="flex items-center gap-2"><Dot tone={tone} /><span className="font-medium">{h.name}</span></div></td>
      <td><Badge tone={h.kind === "service" ? "info" : "muted"}>{h.kind}</Badge></td>
      <td className="mono text-xs">{h.version ?? "—"}</td>
      <td className={cx("mono", `text-${tone}`)}>{pct(h.availability, 2)}</td>
      <td className="mono text-xs">{pct(h.error_rate, 1)}</td>
      <td className="mono text-xs">{ms(h.p95_ms)}</td>
      <td className="mono text-xs">{h.request_rate?.toFixed(1) ?? "—"} rps</td>
      <td>{h.open_incidents ? <Badge tone="crit">{h.open_incidents}</Badge> : <span className="text-fg-dim">0</span>}</td>
      <td className="text-xs text-fg-muted">{ago(h.last_seen)}</td>
      <td>{h.kind === "service" && <Sparkline values={series.data?.map((p) => p.value) ?? []} tone={tone} threshold={0.1} />}</td>
    </tr>
  );
}
