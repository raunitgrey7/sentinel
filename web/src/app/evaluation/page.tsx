"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsyncAction, usePoll, useRequireAuth } from "@/lib/hooks";
import { ago, ms, num, pct, titleCase } from "@/lib/format";
import { Badge, Button, Empty, ErrorNote, Panel, Progress, Skeleton, Stat, Table, cx } from "@/components/ui";
import type { EvaluationRun } from "@/lib/types";

export default function EvaluationPage() {
  const s = useRequireAuth();
  const enabled = s.ready && !!s.token;
  const runs = usePoll(() => api.evalRuns(), 8000, [], enabled);
  const [selected, setSelected] = useState<string | null>(null);
  const run: EvaluationRun | undefined = (runs.data ?? []).find((r) => r.id === selected) ?? (runs.data ?? []).find((r) => r.status === "completed");
  const cases = usePoll(() => (run ? api.evalCases(run.id) : Promise.resolve([])), 10000, [run?.id], enabled && !!run);
  const { busy, error, run: act } = useAsyncAction();
  const sm = run?.summary;
  const canRun = s.user?.role === "SRE" || s.user?.role === "ADMIN";
  const [showWrongOnly, setShowWrongOnly] = useState(false);
  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Evaluation</h1>
          <p className="text-xs text-fg-muted">Synthetic production failures across 14 root-cause categories, healthy controls included. Ground truth never reaches the pipeline.</p>
        </div>
        <div className="flex items-center gap-2">
          {runs.data && runs.data.length > 1 && (
            <select value={run?.id ?? ""} onChange={(e) => setSelected(e.target.value)} className="rounded-md border border-border bg-bg px-2 py-1.5 text-xs text-fg">
              {runs.data.map((r) => <option key={r.id} value={r.id}>{r.name} · {r.status} · {ago(r.started_at)}</option>)}
            </select>
          )}
          <Button variant="primary" disabled={busy || !canRun} onClick={async () => { await act(() => api.startEval(12)); await runs.refresh(); }} title={canRun ? "Runs 12 scenarios in the API process" : "SRE role required"}>▶ Quick run (12)</Button>
        </div>
      </header>
      {error && <ErrorNote>{error}</ErrorNote>}
      {!runs.data ? (
        <Skeleton className="h-40" />
      ) : !run || !sm || !sm.cases ? (
        <Empty>No completed evaluation run yet. Run <span className="mono">make eval</span> (all scenarios) or start a quick run.</Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <Stat label="Cases" value={sm.cases} sub={`${sm.fault_cases} faults · ${sm.control_cases} controls`} tone="accent" />
            <Stat label="Root cause top-1" value={pct(sm.root_cause_accuracy, 1)} tone="ok" sub={`top-3 ${pct(sm.root_cause_top3_accuracy, 1)}`} />
            <Stat label="Detection" value={pct(sm.detection_rate, 1)} tone="info" sub={sm.mean_detection_gap_s ? `onset→alert ${Math.round(sm.mean_detection_gap_s)}s` : undefined} />
            <Stat label="Evidence precision" value={pct(sm.evidence_precision, 1)} tone="violet" sub={`citations valid ${pct(sm.citation_validity, 1)}`} />
            <Stat label="False positives" value={pct(sm.false_positive_rate, 1)} tone={sm.false_positive_rate > 0.1 ? "crit" : "ok"} sub="healthy controls" />
            <Stat label="Confident-wrong" value={pct(sm.confident_wrong_rate, 1)} tone={sm.confident_wrong_rate > 0.05 ? "warn" : "ok"} sub={`wrong & ≥ ${sm.confidence_threshold}`} />
            <Stat label="Calibration (ECE)" value={num(sm.ece, 3)} tone={sm.ece > 0.2 ? "warn" : "ok"} sub="lower is better" />
            <Stat label="Investigation" value={ms(sm.median_investigation_ms)} tone="accent" sub={`p95 ${ms(sm.p95_investigation_ms)} · model ${ms(sm.mean_llm_ms)}`} />
          </div>
          <div className="text-[11px] text-fg-muted">
            Run <span className="mono">{run.name}</span> · provider <span className="mono">{sm.llm_provider ?? run.config.llm_provider as string}</span> / <span className="mono">{sm.model ?? "deterministic"}</span> · {sm.wall_time_s ? `${Math.round(sm.wall_time_s)}s wall` : ""} · {ago(run.completed_at)}
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title="Per fault type" padded={false}>
              <Table>
                <thead><tr><th>Fault</th><th>Cases</th><th>Detected</th><th>Top-1</th><th>Top-3</th><th>Mean conf.</th><th></th></tr></thead>
                <tbody>
                  {Object.entries(sm.per_fault).sort().map(([k, v]) => (
                    <tr key={k}>
                      <td className="mono text-xs">{k}</td>
                      <td className="mono text-xs">{v.cases}</td>
                      <td className="mono text-xs">{v.detected}</td>
                      <td className={cx("mono text-xs", v.accuracy >= 0.9 ? "text-ok" : v.accuracy >= 0.7 ? "text-warn" : "text-crit")}>{pct(v.accuracy)}</td>
                      <td className="mono text-xs">{pct(v.top3_accuracy)}</td>
                      <td className="mono text-xs">{num(v.mean_confidence, 2)}</td>
                      <td className="w-32"><Progress value={v.accuracy} tone={v.accuracy >= 0.9 ? "ok" : v.accuracy >= 0.7 ? "warn" : "crit"} /></td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Panel>
            <Panel title="Confusion (expected → predicted)" padded={false}>
              <Table>
                <thead><tr><th>Expected</th><th>Predicted</th><th>Count</th></tr></thead>
                <tbody>
                  {Object.entries(sm.confusion).flatMap(([exp, preds]) => Object.entries(preds).sort((a, b) => b[1] - a[1]).map(([pred, n]) => (
                    <tr key={exp + pred}>
                      <td className="text-xs">{titleCase(exp)}</td>
                      <td className={cx("text-xs", pred === exp ? "text-ok" : "text-crit")}>{titleCase(pred)}</td>
                      <td className="mono text-xs">{n}</td>
                    </tr>
                  )))}
                </tbody>
              </Table>
            </Panel>
          </div>
          <Panel title={`Cases (${cases.data?.length ?? 0})`} padded={false} action={<label className="flex items-center gap-1.5 text-fg-muted"><input type="checkbox" checked={showWrongOnly} onChange={(e) => setShowWrongOnly(e.target.checked)} /> misses only</label>}>
            {!cases.data ? <div className="p-4"><Skeleton className="h-40" /></div> : (
              <Table>
                <thead><tr><th>Scenario</th><th>Expected</th><th>Predicted</th><th>Conf.</th><th>Evidence prec.</th><th>Latency</th><th>Incident</th></tr></thead>
                <tbody>
                  {cases.data.filter((c) => !showWrongOnly || !c.correct).map((c) => (
                    <tr key={c.id}>
                      <td className="mono text-xs">{c.scenario}</td>
                      <td className="text-xs">{titleCase(c.expected)}</td>
                      <td className="text-xs"><Badge tone={c.correct ? "ok" : "crit"}>{c.predicted ? titleCase(c.predicted) : c.detected ? "—" : "undetected"}</Badge></td>
                      <td className="mono text-xs">{num(c.confidence, 2)}</td>
                      <td className="mono text-xs">{num(c.evidence_precision, 2)}</td>
                      <td className="mono text-xs">{ms(c.latency_ms)}</td>
                      <td className="text-xs">{c.incident_id ? <a href={`/incidents/${c.incident_id}`} className="text-accent hover:underline">open</a> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
