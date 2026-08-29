from sentinel.analysis.dependency_graph import ServiceGraph

EDGES = [("gateway", "auth"), ("gateway", "order"), ("order", "payment"), ("order", "inventory"), ("payment", "postgres"), ("inventory", "postgres")]


def test_downstream_upstream():
    g = ServiceGraph.from_edges(EDGES)
    assert g.downstream("order") == {"payment": 1, "inventory": 1, "postgres": 2}
    assert g.upstream("postgres") == {"payment": 1, "inventory": 1, "order": 2, "gateway": 3}
    assert g.blast_radius("payment") == ["gateway", "order"]


def test_path():
    g = ServiceGraph.from_edges(EDGES)
    assert g.path("gateway", "postgres") == ["gateway", "order", "payment", "postgres"] or g.path("gateway", "postgres") == ["gateway", "order", "inventory", "postgres"]
    assert g.path("auth", "payment") is None


def test_candidate_culprits_prefers_shared_dependency():
    g = ServiceGraph.from_edges(EDGES)
    scores = g.candidate_culprits(["payment", "inventory"])
    assert scores["postgres"] >= scores["payment"]
    assert "gateway" not in scores  # upstream services are victims, not causes


def test_to_dict_and_kinds():
    g = ServiceGraph.from_edges(EDGES, kinds={"postgres": "database"})
    d = g.to_dict()
    assert {"id": "postgres", "kind": "database"} in d["nodes"]
    assert len(d["edges"]) == len(EDGES)
