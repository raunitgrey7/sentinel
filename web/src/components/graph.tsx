"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Graph } from "@/lib/types";

const TYPE_COLOR: Record<string, string> = {
  incident: "#ef4444",
  service: "#60a5fa",
  deployment: "#a78bfa",
  commit: "#a78bfa",
  evidence: "#22d3ee",
  hypothesis: "#f59e0b",
  alert: "#ef4444",
  historical: "#8b98a6",
};
const REL_COLOR: Record<string, string> = {
  supports: "#22c55e",
  contradicts: "#ef4444",
  depends_on: "#2b3a4a",
  affects: "#ef4444",
  hypothesis: "#f59e0b",
  resembles: "#8b98a6",
  correlated_with: "#a78bfa",
};

interface N { key: string; type: string; label: string; x: number; y: number; vx: number; vy: number; r: number; deg: number }

function seed(graph: Graph, edges: Graph["edges"], width: number, height: number): N[] {
  const deg = new Map<string, number>();
  for (const e of edges) {
    deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
    deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
  }
  const ring: Record<string, number> = { incident: 0, hypothesis: 90, service: 150, deployment: 180, commit: 210, alert: 200, evidence: 230, historical: 240 };
  const byType = new Map<string, number>();
  const counts = new Map<string, number>();
  for (const n of graph.nodes) counts.set(n.type, (counts.get(n.type) ?? 0) + 1);
  return graph.nodes.map((n) => {
    const i = byType.get(n.type) ?? 0;
    byType.set(n.type, i + 1);
    const angle = (i / Math.max(counts.get(n.type) ?? 1, 1)) * Math.PI * 2 + (n.type === "evidence" ? 0.3 : 0);
    const rad = ring[n.type] ?? 200;
    return { key: n.key, type: n.type, label: n.label, x: width / 2 + Math.cos(angle) * rad, y: height / 2 + Math.sin(angle) * rad, vx: 0, vy: 0, r: n.type === "incident" ? 16 : n.type === "hypothesis" ? 11 : n.type === "service" ? 9 : 6, deg: deg.get(n.key) ?? 0 };
  });
}

/** Small force-directed layout (no dependency) with type-based radial seeding. */
export function EvidenceGraph({ graph, width = 900, height = 520, onSelect }: { graph: Graph; width?: number; height?: number; onSelect?: (key: string) => void }) {
  const edges = useMemo(() => graph.edges.filter((e) => e.relation !== "observed_on" && e.relation !== "about" && e.relation !== "contains"), [graph]);
  const [nodes, setNodes] = useState<N[]>([]);
  const [hover, setHover] = useState<string | null>(null);
  const dragRef = useRef<string | null>(null);
  const simRef = useRef<N[]>([]);

  useEffect(() => {
    const ns = seed(graph, edges, width, height);
    simRef.current = ns;
    const idx = new Map(ns.map((n) => [n.key, n]));
    let frame = 0;
    let iter = 0;
    const repulsion = 1400 * Math.min(1, 24 / Math.max(ns.length, 1));
    const step = () => {
      const alpha = Math.max(0.02, 0.35 * Math.pow(0.97, iter));
      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const a = ns[i], b = ns[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
          const f = (repulsion * alpha) / d2;
          a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f;
        }
      }
      for (const e of edges) {
        const a = idx.get(e.source), b = idx.get(e.target);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const target = e.relation === "supports" || e.relation === "contradicts" ? 70 : e.relation === "hypothesis" ? 110 : 120;
        const f = ((d - target) / d) * 0.08 * alpha * 4;
        a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
      }
      for (const n of ns) {
        if (n.key === dragRef.current) { n.vx = n.vy = 0; continue; }
        if (n.type === "incident") { n.x += (width / 2 - n.x) * 0.1; n.y += (height / 2 - n.y) * 0.1; }
        n.vx += (width / 2 - n.x) * 0.006 * alpha;
        n.vy += (height / 2 - n.y) * 0.006 * alpha;
        n.x += n.vx; n.y += n.vy; n.vx *= 0.6; n.vy *= 0.6;
        n.x = Math.max(n.r + 4, Math.min(width - n.r - 4, n.x));
        n.y = Math.max(n.r + 4, Math.min(height - n.r - 4, n.y));
      }
      iter++;
      setNodes(ns.map((n) => ({ ...n })));
      if (iter < 220) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [graph, edges, width, height]);

  const idx = useMemo(() => new Map(nodes.map((n) => [n.key, n])), [nodes]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of edges) {
      if (!m.has(e.source)) m.set(e.source, new Set());
      if (!m.has(e.target)) m.set(e.target, new Set());
      m.get(e.source)!.add(e.target);
      m.get(e.target)!.add(e.source);
    }
    return m;
  }, [edges]);
  const dim = (k: string) => hover && hover !== k && !neighbours.get(hover)?.has(k);

  return (
    <div className="relative">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        className="block rounded-md bg-bg"
        onMouseMove={(ev) => {
          const key = dragRef.current;
          if (!key) return;
          const n = simRef.current.find((x) => x.key === key);
          if (!n) return;
          const rect = ev.currentTarget.getBoundingClientRect();
          n.x = ((ev.clientX - rect.left) / rect.width) * width;
          n.y = ((ev.clientY - rect.top) / rect.height) * height;
          setNodes(simRef.current.map((x) => ({ ...x })));
        }}
        onMouseUp={() => { dragRef.current = null; }}
        onMouseLeave={() => { dragRef.current = null; }}
      >
        {edges.map((e, i) => {
          const a = idx.get(e.source), b = idx.get(e.target);
          if (!a || !b) return null;
          const c = REL_COLOR[e.relation] ?? "#2b3a4a";
          const faded = dim(e.source) || dim(e.target);
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={c} strokeWidth={e.relation === "supports" || e.relation === "contradicts" ? 0.8 + e.weight * 1.6 : 1} opacity={faded ? 0.08 : 0.75} strokeDasharray={e.relation === "contradicts" ? "4 3" : e.relation === "resembles" ? "2 3" : undefined} />;
        })}
        {nodes.map((n) => (
          <g key={n.key} transform={`translate(${n.x},${n.y})`} opacity={dim(n.key) ? 0.15 : 1} style={{ cursor: "pointer" }} onMouseEnter={() => setHover(n.key)} onMouseLeave={() => setHover(null)} onMouseDown={() => { dragRef.current = n.key; }} onClick={() => onSelect?.(n.key)}>
            <circle r={n.r} fill={TYPE_COLOR[n.type] ?? "#8b98a6"} fillOpacity={0.18} stroke={TYPE_COLOR[n.type] ?? "#8b98a6"} strokeWidth={n.type === "hypothesis" || n.type === "incident" ? 2 : 1.2} />
            {(n.type !== "evidence" || hover === n.key || n.deg > 3) && (
              <text y={n.r + 11} textAnchor="middle" fontSize={n.type === "incident" ? 11 : 9} fill="#e6edf3" fontFamily="var(--font-geist-sans)" style={{ pointerEvents: "none" }}>
                {n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label}
              </text>
            )}
            {n.type === "evidence" && <text textAnchor="middle" y={3} fontSize={7} fill="#22d3ee" fontFamily="var(--font-geist-mono)" style={{ pointerEvents: "none" }}>{n.label.split(" ")[0]}</text>}
          </g>
        ))}
      </svg>
      <div className="absolute bottom-2 left-2 flex flex-wrap gap-2 rounded bg-bg/80 px-2 py-1 text-[10px] text-fg-muted">
        {Object.entries(TYPE_COLOR).filter(([t]) => ["incident", "service", "deployment", "evidence", "hypothesis", "historical"].includes(t)).map(([t, c]) => (
          <span key={t} className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />{t}</span>
        ))}
        <span className="flex items-center gap-1"><span className="inline-block h-px w-4" style={{ background: "#22c55e" }} />supports</span>
        <span className="flex items-center gap-1"><span className="inline-block h-px w-4 border-t border-dashed" style={{ borderColor: "#ef4444" }} />contradicts</span>
      </div>
    </div>
  );
}
