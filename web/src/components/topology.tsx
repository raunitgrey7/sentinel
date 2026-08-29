"use client";

import { useMemo } from "react";
import type { ServiceHealth, Topology } from "@/lib/types";

/** Layered DAG layout: nodes are placed by longest-path depth from the roots (callers). */
export function TopologyView({ topology, health, highlight }: { topology: Topology; health?: ServiceHealth[]; highlight?: string[] }) {
  const layout = useMemo(() => {
    const ids = topology.nodes.map((n) => n.id);
    const incoming = new Map<string, number>(ids.map((i) => [i, 0]));
    const out = new Map<string, string[]>(ids.map((i) => [i, []]));
    for (const e of topology.edges) {
      incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
      out.get(e.source)?.push(e.target);
    }
    const depth = new Map<string, number>();
    const queue = ids.filter((i) => (incoming.get(i) ?? 0) === 0);
    queue.forEach((q) => depth.set(q, 0));
    // longest path layering
    const order: string[] = [];
    const indeg = new Map(incoming);
    const q2 = [...queue];
    while (q2.length) {
      const n = q2.shift()!;
      order.push(n);
      for (const t of out.get(n) ?? []) {
        depth.set(t, Math.max(depth.get(t) ?? 0, (depth.get(n) ?? 0) + 1));
        indeg.set(t, (indeg.get(t) ?? 1) - 1);
        if ((indeg.get(t) ?? 0) === 0) q2.push(t);
      }
    }
    ids.forEach((i) => { if (!depth.has(i)) depth.set(i, 0); });
    const cols = new Map<number, string[]>();
    for (const i of ids) {
      const d = depth.get(i) ?? 0;
      cols.set(d, [...(cols.get(d) ?? []), i]);
    }
    const colW = 190;
    const rowH = 64;
    const maxRows = Math.max(...[...cols.values()].map((c) => c.length), 1);
    const height = maxRows * rowH + 40;
    const pos = new Map<string, { x: number; y: number }>();
    for (const [d, items] of cols) {
      items.sort();
      const offset = (height - items.length * rowH) / 2;
      items.forEach((id, i) => pos.set(id, { x: d * colW + 90, y: offset + i * rowH + rowH / 2 }));
    }
    const width = (cols.size || 1) * colW + 40;
    return { pos, width, height };
  }, [topology]);

  const healthMap = new Map((health ?? []).map((h) => [h.name, h]));
  const kinds = new Map(topology.nodes.map((n) => [n.id, n.kind]));
  const hl = new Set(highlight ?? []);
  return (
    <div className="overflow-x-auto scroll-thin">
      <svg width={layout.width} height={layout.height} className="block">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#2b3a4a" />
          </marker>
        </defs>
        {topology.edges.map((e, i) => {
          const a = layout.pos.get(e.source);
          const b = layout.pos.get(e.target);
          if (!a || !b) return null;
          const hot = hl.has(e.source) && hl.has(e.target);
          const mx = (a.x + b.x) / 2;
          return <path key={i} d={`M${a.x + 70},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x - 70},${b.y}`} fill="none" stroke={hot ? "#ef4444" : "#2b3a4a"} strokeWidth={hot ? 2 : 1.2} markerEnd="url(#arrow)" opacity={hot ? 0.9 : 0.8} />;
        })}
        {topology.nodes.map((n) => {
          const p = layout.pos.get(n.id)!;
          const h = healthMap.get(n.id);
          const kind = kinds.get(n.id) ?? "service";
          const tone = h ? (!h.healthy ? "#ef4444" : h.availability < 0.99 ? "#f59e0b" : "#22c55e") : "#5d6b79";
          const isHl = hl.has(n.id);
          const shape = kind === "database" ? "db" : kind === "cache" ? "cache" : kind === "queue" ? "queue" : kind === "external" ? "ext" : "svc";
          return (
            <g key={n.id} transform={`translate(${p.x - 70},${p.y - 20})`}>
              <rect width={140} height={40} rx={shape === "svc" ? 8 : 20} fill={isHl ? "rgba(239,68,68,0.10)" : "#121a23"} stroke={isHl ? "#ef4444" : "#2b3a4a"} strokeWidth={isHl ? 1.5 : 1} strokeDasharray={shape === "ext" ? "4 3" : undefined} />
              <circle cx={14} cy={20} r={4} fill={tone} />
              <text x={26} y={17} fill="#e6edf3" fontSize={11} fontFamily="var(--font-geist-sans)" fontWeight={600}>{n.id.length > 18 ? n.id.slice(0, 17) + "…" : n.id}</text>
              <text x={26} y={30} fill="#8b98a6" fontSize={9} fontFamily="var(--font-geist-mono)">
                {h && kind === "service" ? `${((h.error_rate ?? 0) * 100).toFixed(1)}% err · ${Math.round(h.p95_ms ?? 0)}ms` : kind}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
