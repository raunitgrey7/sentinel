export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}s`;
  return `${Math.round(v)}ms`;
}

export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

export function timeHM(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString([], { month: "short", day: "2-digit" })} ${timeHM(iso)}`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function duration(fromIso: string | null | undefined, toIso: string | null | undefined): string {
  if (!fromIso) return "—";
  const end = toIso ? new Date(toIso).getTime() : Date.now();
  const s = Math.max(0, (end - new Date(fromIso).getTime()) / 1000);
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const STATUS_TONE: Record<string, "ok" | "warn" | "crit" | "info" | "muted" | "accent"> = {
  DETECTED: "crit",
  TRIAGING: "warn",
  INVESTIGATING: "accent",
  INVESTIGATION_FAILED: "crit",
  RETRYING: "warn",
  ROOT_CAUSE_IDENTIFIED: "info",
  LOW_CONFIDENCE: "warn",
  HUMAN_REVIEW: "warn",
  REMEDIATION_PROPOSED: "info",
  AWAITING_HUMAN: "warn",
  RESOLVED: "ok",
  POSTMORTEM: "ok",
  CLOSED: "muted",
};

export const SEVERITY_TONE: Record<string, "ok" | "warn" | "crit" | "info" | "muted"> = {
  CRITICAL: "crit",
  HIGH: "crit",
  MEDIUM: "warn",
  LOW: "info",
  INFO: "muted",
};

export function confidenceTone(c: number | null | undefined): "ok" | "warn" | "crit" | "muted" {
  if (c === null || c === undefined) return "muted";
  if (c >= 0.75) return "ok";
  if (c >= 0.55) return "warn";
  return "crit";
}
