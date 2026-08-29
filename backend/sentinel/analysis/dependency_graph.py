"""Service dependency graph: blast radius, upstream/downstream walks, path finding.

Edges point from caller → callee. "Downstream" of X = things X calls (potential *causes*
of X's failure); "upstream" of X = things that call X (potential *victims*).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class ServiceGraph:
    nodes: set[str] = field(default_factory=set)
    out_edges: dict[str, set[str]] = field(default_factory=dict)
    in_edges: dict[str, set[str]] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_edges(cls, edges: list[tuple[str, str]], kinds: dict[str, str] | None = None) -> ServiceGraph:
        g = cls()
        for s, t in edges:
            g.add_edge(s, t)
        if kinds:
            g.kinds.update(kinds)
        return g

    def add_node(self, n: str, kind: str = "service") -> None:
        self.nodes.add(n)
        self.kinds.setdefault(n, kind)
        self.out_edges.setdefault(n, set())
        self.in_edges.setdefault(n, set())

    def add_edge(self, source: str, target: str) -> None:
        self.add_node(source)
        self.add_node(target)
        self.out_edges[source].add(target)
        self.in_edges[target].add(source)

    def downstream(self, n: str, max_depth: int = 5) -> dict[str, int]:
        """Callees reachable from ``n`` → depth."""
        return self._walk(n, self.out_edges, max_depth)

    def upstream(self, n: str, max_depth: int = 5) -> dict[str, int]:
        """Callers that (transitively) depend on ``n`` → depth."""
        return self._walk(n, self.in_edges, max_depth)

    def _walk(self, start: str, adj: dict[str, set[str]], max_depth: int) -> dict[str, int]:
        seen: dict[str, int] = {}
        dq: deque[tuple[str, int]] = deque([(start, 0)])
        while dq:
            cur, d = dq.popleft()
            if d >= max_depth:
                continue
            for nxt in adj.get(cur, ()):
                if nxt not in seen and nxt != start:
                    seen[nxt] = d + 1
                    dq.append((nxt, d + 1))
        return seen

    def path(self, source: str, target: str) -> list[str] | None:
        prev: dict[str, str | None] = {source: None}
        dq: deque[str] = deque([source])
        while dq:
            cur = dq.popleft()
            if cur == target:
                out = []
                node: str | None = cur
                while node is not None:
                    out.append(node)
                    node = prev[node]
                return list(reversed(out))
            for nxt in self.out_edges.get(cur, ()):
                if nxt not in prev:
                    prev[nxt] = cur
                    dq.append(nxt)
        return None

    def blast_radius(self, n: str) -> list[str]:
        return sorted(self.upstream(n))

    def candidate_culprits(self, affected: list[str]) -> dict[str, float]:
        """Score nodes by how well they explain the affected set.

        A node that is downstream of *every* affected service (a shared dependency) is a
        strong candidate; the affected services themselves are always candidates.
        """
        scores: dict[str, float] = {}
        if not affected:
            return scores
        for a in affected:
            scores[a] = max(scores.get(a, 0.0), 0.6)
            for dep, depth in self.downstream(a).items():
                scores[dep] = scores.get(dep, 0.0) + (1.0 / depth) / len(affected)
        return {k: round(min(v, 1.0), 3) for k, v in scores.items()}

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [{"id": n, "kind": self.kinds.get(n, "service")} for n in sorted(self.nodes)],
            "edges": [{"source": s, "target": t} for s in sorted(self.out_edges) for t in sorted(self.out_edges[s])],
        }
