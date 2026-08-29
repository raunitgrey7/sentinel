"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAsyncAction, usePoll, useRequireAuth, useSession } from "@/lib/hooks";
import { ago, dateTime, duration, SEVERITY_TONE, STATUS_TONE } from "@/lib/format";
import { Badge, Button, ErrorNote, Panel, Skeleton, Tabs, cx } from "@/components/ui";
import { RootCauseCard } from "@/components/incident/root-cause";
import { ClusterList, EvidenceList } from "@/components/incident/evidence";
import { TimelineView } from "@/components/incident/timeline";
import { InvestigationSteps } from "@/components/incident/steps";
import { HypothesesList } from "@/components/incident/hypotheses";
import { WhyPanel } from "@/components/incident/why";
import { RemediationPanel } from "@/components/incident/remediation";
import { PostmortemPanel } from "@/components/incident/postmortem";
import { EvidenceGraph } from "@/components/graph";
import type { Postmortem } from "@/lib/types";

type Tab = "evidence" | "hypotheses" | "why" | "graph" | "remediation" | "postmortem" | "clusters";

export default function IncidentPage() {
  const s = useRequireAuth();
  const session = useSession();
  const { id } = useParams<{ id: string }>();
  const enabled = s.ready && !!s.token && !!id;
  const inc = usePoll(() => api.incident(id), 4000, [id], enabled);
  const active = !!inc.data && ["DETECTED", "TRIAGING", "INVESTIGATING", "RETRYING"].includes(inc.data.status);
  const fast = active ? 2000 : 8000;
  const timeline = usePoll(() => api.timeline(id), fast, [id, fast], enabled);
  const evidence = usePoll(() => api.evidence(id), fast, [id, fast], enabled);
  const hyps = usePoll(() => api.hypotheses(id), fast, [id, fast], enabled);
  const invs = usePoll(() => api.investigations(id), fast, [id, fast], enabled);
  const remediation = usePoll(() => api.remediation(id), fast, [id, fast], enabled);
  const clusters = usePoll(() => api.clusters(id), 15000, [id], enabled);
  const graph = usePoll(() => api.graph(id), 10000, [id], enabled);
  const pmPoll = usePoll<Postmortem | null>(
    () =>
      api.postmortem(id).catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }),
    15000,
    [id],
    enabled,
  );
  const pm = pmPoll.data;
  const loadPm = pmPoll.refresh;

  const [tab, setTab] = useState<Tab>("evidence");
  const [highlight, setHighlight] = useState<string | null>(null);
  const jumpToRef = (ref: string) => {
    setTab("evidence");
    setHighlight(ref);
    setTimeout(() => document.getElementById(`evidence-${ref}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  const { busy, error, run } = useAsyncAction();
  const latestInv = invs.data?.[0] ?? null;
  const top = useMemo(() => hyps.data?.[0] ?? null, [hyps.data]);
  const i = inc.data;
  const isEng = ["ENGINEER", "SRE", "ADMIN"].includes(session.user?.role ?? "");

  if (!i) {
    return inc.error ? <ErrorNote>{inc.error}</ErrorNote> : <div className="space-y-3"><Skeleton className="h-10" /><Skeleton className="h-40" /></div>;
  }
  const contradicting = (evidence.data ?? []).filter((e) => e.direction === "contradicts").length;
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-fg-muted">
            <Link href="/incidents" className="hover:text-fg">Incidents</Link><span>/</span><span className="mono">{i.key}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold">{i.title}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={SEVERITY_TONE[i.severity] ?? "muted"}>{i.severity}</Badge>
            <Badge tone={STATUS_TONE[i.status] ?? "muted"} dot>{i.status.replace(/_/g, " ")}</Badge>
            <span className="text-fg-muted">primary <span className="text-fg">{i.primary_service}</span></span>
            <span className="text-fg-muted">· blast radius {i.affected_services.filter((x) => x !== i.primary_service).join(", ") || "none"}</span>
            <span className="text-fg-muted" title={dateTime(i.started_at)}>· onset {ago(i.started_at)}</span>
            <span className="text-fg-muted" title={dateTime(i.detected_at)}>· detected {ago(i.detected_at)}</span>
            <span className="text-fg-muted">· duration {duration(i.started_at, i.resolved_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isEng && <Button onClick={async () => { await run(() => api.investigate(id)); await invs.refresh(); }} disabled={busy || active}>↻ Re-investigate</Button>}
          {isEng && !["RESOLVED", "POSTMORTEM", "CLOSED"].includes(i.status) && (
            <Button variant="primary" onClick={async () => { const notes = window.prompt("Resolution notes") ?? ""; await run(() => api.resolve(id, notes)); await inc.refresh(); }} disabled={busy}>✓ Resolve</Button>
          )}
          {isEng && i.status === "RESOLVED" && <Button onClick={async () => { await run(() => api.transition(id, "POSTMORTEM")); await inc.refresh(); }} disabled={busy}>→ Postmortem</Button>}
        </div>
      </header>
      {error && <ErrorNote>{error}</ErrorNote>}

      <RootCauseCard incident={i} top={top} evidence={evidence.data ?? []} investigation={latestInv} onRef={jumpToRef} />

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title="Investigation" className="xl:col-span-1">
          <InvestigationSteps investigation={latestInv} />
          {invs.data && invs.data.length > 1 && <div className="mt-2 text-[11px] text-fg-dim">{invs.data.length} attempts recorded</div>}
        </Panel>
        <Panel title="Timeline" className="xl:col-span-2">
          {timeline.data ? <TimelineView events={timeline.data} onset={i.started_at} /> : <Skeleton className="h-32" />}
        </Panel>
      </div>

      <Panel padded={false}>
        <div className="px-4 pt-2">
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "evidence", label: "Evidence", count: evidence.data?.length },
              { id: "hypotheses", label: "Hypotheses", count: hyps.data?.length },
              { id: "why", label: "Why?" },
              { id: "graph", label: "Evidence graph" },
              { id: "remediation", label: "Remediation", count: remediation.data?.length },
              { id: "postmortem", label: "Postmortem" },
              { id: "clusters", label: "Error clusters", count: clusters.data?.length },
            ]}
          />
        </div>
        <div className="p-4">
          {tab === "evidence" && (
            <div>
              <div className="mb-2 text-[11px] text-fg-muted">{evidence.data?.length ?? 0} evidence items · {contradicting} contradicting · hover a hypothesis citation to highlight</div>
              {evidence.data ? <EvidenceList evidence={evidence.data} highlight={highlight} onHighlight={setHighlight} /> : <Skeleton className="h-40" />}
            </div>
          )}
          {tab === "hypotheses" && (hyps.data ? <HypothesesList hypotheses={hyps.data} onRef={jumpToRef} /> : <Skeleton className="h-40" />)}
          {tab === "why" && <WhyPanel incidentId={id} hypotheses={hyps.data ?? []} onRef={jumpToRef} />}
          {tab === "graph" && (graph.data && graph.data.nodes.length ? <EvidenceGraph graph={graph.data} onSelect={(k) => { if (k.startsWith("evidence:")) jumpToRef(k.split(":")[1]); }} /> : <Skeleton className="h-80" />)}
          {tab === "remediation" && (remediation.data ? <RemediationPanel incidentId={id} actions={remediation.data} onChange={() => { void remediation.refresh(); void inc.refresh(); void timeline.refresh(); }} /> : <Skeleton className="h-32" />)}
          {tab === "postmortem" && <PostmortemPanel incidentId={id} postmortem={pm} canGenerate={!active} onChange={() => { void loadPm(); void inc.refresh(); }} onRef={jumpToRef} />}
          {tab === "clusters" && (clusters.data ? <ClusterList clusters={clusters.data} /> : <Skeleton className="h-32" />)}
        </div>
      </Panel>
      <div className={cx("text-[11px] text-fg-dim")}>id <span className="mono">{i.id}</span> · created by {i.created_by} · {i.description}</div>
    </div>
  );
}
