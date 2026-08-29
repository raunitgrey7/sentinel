"use client";

import { api } from "@/lib/api";
import { useAsyncAction, useSession } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { Badge, Button, Empty, ErrorNote, cx } from "@/components/ui";
import type { Remediation } from "@/lib/types";

const STATUS_TONE: Record<Remediation["status"], "ok" | "warn" | "crit" | "info" | "muted" | "accent"> = {
  proposed: "muted",
  approved: "info",
  rejected: "crit",
  executing: "accent",
  executed: "ok",
  failed: "crit",
  verified: "ok",
};

export function RemediationPanel({ incidentId, actions, onChange }: { incidentId: string; actions: Remediation[]; onChange: () => void }) {
  const s = useSession();
  const role = s.user?.role ?? "VIEWER";
  const isEng = ["ENGINEER", "SRE", "ADMIN"].includes(role);
  const isSre = ["SRE", "ADMIN"].includes(role);
  const { busy, error, run } = useAsyncAction();
  const act = async (a: Remediation, verb: "request" | "approve" | "reject" | "execute") => {
    const note = verb === "execute" ? "" : window.prompt(`${verb} "${a.title}" — note (optional)`) ?? "";
    await run(() => api.remediationAction(incidentId, a.id, verb, note));
    onChange();
  };
  if (!actions.length) return <Empty>No remediation proposed yet.</Empty>;
  return (
    <div className="space-y-2">
      {error && <ErrorNote>{error}</ErrorNote>}
      <p className="text-[11px] text-fg-muted">Recommendation-only by default. An engineer <em>requests</em>, a different SRE <em>approves</em>, then execution runs through the target adapter and is verified. Every step is audited.</p>
      <ul className="space-y-2">
        {actions.map((a) => (
          <li key={a.id} className="rounded-md border border-border bg-bg-elev p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{a.title}</span>
              <Badge tone={STATUS_TONE[a.status]} dot>{a.status}</Badge>
              <Badge tone={a.risk === "high" ? "crit" : a.risk === "medium" ? "warn" : "muted"}>{a.risk} risk</Badge>
              <Badge tone="muted">{a.kind}</Badge>
              {!a.executable && <span className="text-[11px] text-fg-dim">advisory</span>}
            </div>
            {a.description && <p className="mt-1 text-xs text-fg-muted">{a.description}</p>}
            {Object.keys(a.params).length > 0 && <div className="mt-1 mono text-[11px] text-fg-dim">{Object.entries(a.params).map(([k, v]) => `${k}=${String(v)}`).join("  ")}</div>}
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-fg-muted">
              {a.requested_by && <span>requested by <span className="text-fg">{a.requested_by.slice(0, 8)}</span></span>}
              {a.approved_by && <span>· approved by <span className="text-fg">{a.approved_by.slice(0, 8)}</span></span>}
              {a.approval_note && <span>· “{a.approval_note}”</span>}
              {a.executed_at && <span>· executed {ago(a.executed_at)}</span>}
              {a.result?.verify !== undefined && <span className={cx((a.result.verify as { ok?: boolean }).ok ? "text-ok" : "text-warn")}>· verification {(a.result.verify as { ok?: boolean }).ok ? "passed" : "pending"}</span>}
              {a.result?.error !== undefined && <span className="text-crit">· {String(a.result.error)}</span>}
              <span className="ml-auto flex gap-1">
                {a.status === "proposed" && isEng && !a.requested_by && <Button onClick={() => act(a, "request")} disabled={busy}>Request</Button>}
                {a.status === "proposed" && isSre && <Button variant="primary" onClick={() => act(a, "approve")} disabled={busy}>Approve</Button>}
                {(a.status === "proposed" || a.status === "approved") && isSre && <Button variant="danger" onClick={() => act(a, "reject")} disabled={busy}>Reject</Button>}
                {a.status === "approved" && a.executable && isSre && <Button variant="primary" onClick={() => act(a, "execute")} disabled={busy}>▶ Execute</Button>}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
