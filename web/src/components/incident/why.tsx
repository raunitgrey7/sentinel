"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAsyncAction } from "@/lib/hooks";
import { ms, pct } from "@/lib/format";
import { Button, ErrorNote, Spinner } from "@/components/ui";
import type { Hypothesis, WhyAnswer } from "@/lib/types";

const SUGGESTIONS = ["Why do you think the deployment caused this?", "Why not CPU saturation?", "What evidence contradicts this?", "How confident should I be, honestly?"];

export function WhyPanel({ incidentId, hypotheses, onRef }: { incidentId: string; hypotheses: Hypothesis[]; onRef?: (ref: string) => void }) {
  const [question, setQuestion] = useState("");
  const [hyp, setHyp] = useState<string>(hypotheses[0]?.id ?? "");
  const [answers, setAnswers] = useState<{ q: string; a: WhyAnswer }[]>([]);
  const { busy, error, run } = useAsyncAction();
  const ask = async (q: string) => {
    if (!q.trim()) return;
    const out = await run(() => api.why(incidentId, q, hyp || undefined));
    if (out) {
      setAnswers((xs) => [{ q, a: out }, ...xs]);
      setQuestion("");
    }
  };
  const renderWithRefs = (text: string) => {
    const parts = text.split(/(\[E\d+\]|\bE\d+\b)/g);
    return parts.map((p, i) => {
      const m = p.match(/E\d+/);
      if (m && (p.startsWith("[") || /^E\d+$/.test(p))) {
        return <button key={i} onClick={() => onRef?.(m[0])} className="mono mx-0.5 rounded bg-accent-soft px-1 text-[11px] text-accent hover:brightness-125">{m[0]}</button>;
      }
      return <span key={i}>{p}</span>;
    });
  };
  return (
    <div className="space-y-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
        className="flex gap-2"
      >
        <select value={hyp} onChange={(e) => setHyp(e.target.value)} className="max-w-[220px] rounded-md border border-border bg-bg px-2 text-xs text-fg" title="Hypothesis under discussion">
          {hypotheses.map((h) => <option key={h.id} value={h.id}>#{h.rank} {h.title}</option>)}
        </select>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Challenge the investigation…" className="flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg outline-none focus:border-accent" />
        <Button type="submit" variant="primary" disabled={busy || !question.trim()}>{busy ? <Spinner /> : "Why?"}</Button>
      </form>
      <div className="flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => <button key={s} onClick={() => void ask(s)} disabled={busy} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-fg-muted hover:border-accent/60 hover:text-fg">{s}</button>)}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="space-y-3">
        {answers.map(({ q, a }, i) => (
          <div key={i} className="rounded-md border border-border bg-bg-elev p-3 text-sm">
            <div className="text-xs text-fg-muted">Q · {q}</div>
            <div className="mt-2 whitespace-pre-wrap leading-relaxed">{renderWithRefs(a.answer)}</div>
            {a.conclusion && <div className="mt-2 border-t border-border pt-2 text-fg">{renderWithRefs(a.conclusion)}</div>}
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-fg-muted">
              <span>supporting {a.supporting.length}</span>
              <span>· counter-evidence {a.counter_evidence.length}</span>
              {a.invalid_citations_dropped > 0 && <span className="text-warn">· {a.invalid_citations_dropped} invalid citation(s) dropped by the verifier</span>}
              <span>· hypothesis confidence {pct(a.hypothesis.confidence)}</span>
              <span className="ml-auto mono">{a.provider}{a.model ? `/${a.model}` : ""} · {ms(a.latency_ms)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
