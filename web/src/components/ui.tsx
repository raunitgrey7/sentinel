"use client";

import type { ReactNode } from "react";

type Tone = "ok" | "warn" | "crit" | "info" | "muted" | "accent" | "violet";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  crit: "text-crit",
  info: "text-info",
  muted: "text-fg-muted",
  accent: "text-accent",
  violet: "text-violet",
};
const TONE_BG: Record<Tone, string> = {
  ok: "bg-ok/12 text-ok border-ok/30",
  warn: "bg-warn/12 text-warn border-warn/30",
  crit: "bg-crit/12 text-crit border-crit/30",
  info: "bg-info/12 text-info border-info/30",
  muted: "bg-fg-dim/15 text-fg-muted border-border-strong",
  accent: "bg-accent/12 text-accent border-accent/30",
  violet: "bg-violet/12 text-violet border-violet/30",
};
const TONE_DOT: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  crit: "bg-crit",
  info: "bg-info",
  muted: "bg-fg-dim",
  accent: "bg-accent",
  violet: "bg-violet",
};

export function cx(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(" ");
}

export function Panel({ title, action, children, className, padded = true }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={cx("panel", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3 pb-2 border-b border-border">
          <h2 className="panel-title">{title}</h2>
          {action && <div className="flex items-center gap-2 text-xs">{action}</div>}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Badge({ tone = "muted", children, className, dot }: { tone?: Tone; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap", TONE_BG[tone], className)}>
      {dot && <span className={cx("h-1.5 w-1.5 rounded-full", TONE_DOT[tone])} />}
      {children}
    </span>
  );
}

export function Dot({ tone = "muted", pulse }: { tone?: Tone; pulse?: boolean }) {
  return <span className={cx("inline-block h-2 w-2 rounded-full", TONE_DOT[tone], pulse && "pulse")} />;
}

export function Stat({ label, value, sub, tone = "muted", className }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; className?: string }) {
  return (
    <div className={cx("panel px-4 py-3", className)}>
      <div className="panel-title">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold mono", TONE_TEXT[tone])}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-fg-muted">{sub}</div>}
    </div>
  );
}

export function Button({ children, onClick, variant = "default", disabled, type = "button", className, title }: { children: ReactNode; onClick?: () => void; variant?: "default" | "primary" | "danger" | "ghost"; disabled?: boolean; type?: "button" | "submit"; className?: string; title?: string }) {
  const base = "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-40 disabled:cursor-not-allowed";
  const styles = {
    default: "border border-border-strong bg-panel-2 hover:border-accent/60 hover:text-fg",
    primary: "bg-accent text-[#06232a] hover:brightness-110",
    danger: "border border-crit/40 text-crit hover:bg-crit/10",
    ghost: "text-fg-muted hover:text-fg hover:bg-panel-2",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={cx(base, styles, className)} title={title}>
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span className={cx("inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-border-strong border-t-accent", className)} />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-fg-muted">{children}</div>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-crit/40 bg-crit/10 px-3 py-2 text-xs text-crit">{children}</div>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mono rounded border border-border-strong bg-panel-2 px-1 text-[10px] text-fg-muted">{children}</kbd>;
}

export function Progress({ value, tone = "accent", className }: { value: number; tone?: Tone; className?: string }) {
  return (
    <div className={cx("h-1.5 w-full overflow-hidden rounded bg-panel-2", className)}>
      <div className={cx("h-full rounded transition-all", TONE_DOT[tone])} style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function Sparkline({ values, tone = "accent", width = 120, height = 28, threshold }: { values: number[]; tone?: Tone; width?: number; height?: number; threshold?: number }) {
  if (!values.length) return <svg width={width} height={height} />;
  const max = Math.max(...values, threshold ?? -Infinity, 1e-9);
  const min = Math.min(...values, threshold ?? Infinity, 0);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * width},${height - ((v - min) / span) * (height - 2) - 1}`);
  const color = { ok: "#22c55e", warn: "#f59e0b", crit: "#ef4444", info: "#60a5fa", muted: "#8b98a6", accent: "#22d3ee", violet: "#a78bfa" }[tone];
  const thrY = threshold !== undefined ? height - ((threshold - min) / span) * (height - 2) - 1 : null;
  return (
    <svg width={width} height={height} className="overflow-visible">
      {thrY !== null && <line x1={0} x2={width} y1={thrY} y2={thrY} stroke="#ef4444" strokeDasharray="2 3" strokeWidth={1} opacity={0.6} />}
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1].split(",")[0]} cy={pts[pts.length - 1].split(",")[1]} r={2} fill={color} />
    </svg>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode; count?: number }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cx("-mb-px border-b-2 px-3 py-2 text-xs font-medium transition", value === t.id ? "border-accent text-fg" : "border-transparent text-fg-muted hover:text-fg")}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 rounded bg-panel-2 px-1 text-[10px] text-fg-muted mono">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto scroll-thin", className)}>
      <table className="w-full text-left text-sm [&_th]:panel-title [&_th]:px-3 [&_th]:py-2 [&_th]:font-semibold [&_td]:px-3 [&_td]:py-2 [&_td]:border-t [&_td]:border-border [&_tr:hover_td]:bg-panel-2/60">{children}</table>
    </div>
  );
}
