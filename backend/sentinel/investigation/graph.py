"""Evidence graph: incident ⇢ services ⇢ deployments/commits ⇢ evidence ⇢ hypotheses.

Built in memory from the investigation context, then persisted to ``graph_nodes`` /
``graph_edges``. Also answers structural questions used by the verifier and the "Why?"
endpoint (which evidence supports which hypothesis, what path connects a commit to the
failing request).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sentinel.analysis.dependency_graph import ServiceGraph
from sentinel.investigation.context import EvidenceBag
from sentinel.investigation.scoring import Candidate


@dataclass
class EvidenceGraph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def node(self, key: str, type_: str, label: str, **data: Any) -> str:
        if key not in self.nodes:
            self.nodes[key] = {"key": key, "type": type_, "label": label, "data": data}
        else:
            self.nodes[key]["data"].update(data)
        return key

    def edge(self, source: str, target: str, relation: str, weight: float = 1.0, **data: Any) -> None:
        if source in self.nodes and target in self.nodes:
            self.edges.append({"source": source, "target": target, "relation": relation, "weight": weight, "data": data})

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": self.edges}


def build_graph(
    *,
    incident_key: str,
    incident_title: str,
    primary: str,
    affected: list[str],
    service_graph: ServiceGraph,
    scope: list[str],
    bag: EvidenceBag,
    candidates: list[Candidate],
    deployments: list[dict[str, Any]],
    historical: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> EvidenceGraph:
    g = EvidenceGraph()
    inc = g.node(f"incident:{incident_key}", "incident", incident_key, title=incident_title)

    for svc in sorted(set([primary, *affected, *scope])):
        g.node(f"service:{svc}", "service", svc, kind=service_graph.kinds.get(svc, "service"), primary=svc == primary, affected=svc in affected)
    for svc in [primary, *affected]:
        g.edge(inc, f"service:{svc}", "affects")
    for src, targets in service_graph.out_edges.items():
        for tgt in targets:
            if f"service:{src}" in g.nodes and f"service:{tgt}" in g.nodes:
                g.edge(f"service:{src}", f"service:{tgt}", "depends_on")

    for a in alerts:
        k = g.node(f"alert:{a['id']}", "alert", a["rule_name"], severity=a.get("severity"), service=a.get("service"))
        g.edge(inc, k, "triggered_by")

    for d in deployments:
        dk = g.node(f"deployment:{d['id']}", "deployment", f"{d['service']}:{d['version']}", **{k: d[k] for k in ("service", "version", "deployed_at", "proximity") if k in d})
        g.edge(f"service:{d['service']}", dk, "deployed_version")
        g.edge(inc, dk, "correlated_with", weight=float(d.get("proximity", 0.5)))
        if d.get("commit_sha"):
            ck = g.node(f"commit:{d['commit_sha']}", "commit", d["commit_sha"][:8], message=d.get("commit_message", ""), files=d.get("changed_files", []))
            g.edge(dk, ck, "contains")

    for e in bag.items:
        ek = g.node(f"evidence:{e.ref}", "evidence", f"{e.ref} {e.summary[:60]}", kind=e.kind, weight=e.weight, direction=e.direction, signals=e.signals, source=e.source, service=e.service)
        g.edge(inc, ek, "contains", weight=e.weight)
        if e.service and f"service:{e.service}" in g.nodes:
            g.edge(ek, f"service:{e.service}", "observed_on")
        if e.kind == "deployment" and e.detail.get("deployment_id"):
            g.edge(ek, f"deployment:{e.detail['deployment_id']}", "about")

    for c in candidates:
        hk = g.node(f"hypothesis:{c.category}", "hypothesis", c.title, score=c.score, rank=c.rank, culprit=c.culprit_service)
        g.edge(inc, hk, "hypothesis", weight=c.score)
        if c.culprit_service and f"service:{c.culprit_service}" in g.nodes:
            g.edge(hk, f"service:{c.culprit_service}", "implicates")
        for r in c.supporting:
            g.edge(f"evidence:{r}", hk, "supports", weight=(bag.get(r).weight if bag.get(r) else 1.0))
        for r in c.contradicting:
            g.edge(f"evidence:{r}", hk, "contradicts", weight=(bag.get(r).weight if bag.get(r) else 1.0))

    for h in historical:
        hk = g.node(f"historical:{h['key']}", "historical", h["key"], similarity=h["similarity"], category=h.get("root_cause_category"))
        g.edge(inc, hk, "resembles", weight=float(h["similarity"]))

    return g
