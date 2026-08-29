"""Incident signature: a compact, vocabulary-controlled description used for retrieval.

Signatures are built from Sentinel's own outputs (services, signals, error templates,
categories) rather than free text, so that similarity reflects *failure shape* rather
than wording.
"""

from __future__ import annotations

from typing import Any


def build_signature(
    *,
    primary_service: str,
    affected: list[str],
    signals: dict[str, float],
    error_templates: list[str],
    root_cause_category: str | None = None,
    severity: str | None = None,
) -> str:
    strong = [s for s, w in sorted(signals.items(), key=lambda kv: -kv[1]) if w >= 0.3][:12]
    parts = [
        f"service {primary_service}",
        "affected " + " ".join(sorted(affected)) if affected else "",
        "signals " + " ".join(strong) if strong else "",
        "errors " + " | ".join(t[:80] for t in error_templates[:5]) if error_templates else "",
        f"category {root_cause_category}" if root_cause_category else "",
        f"severity {severity}" if severity else "",
    ]
    return "\n".join(p for p in parts if p)


def signature_from_incident(incident: Any, signals: dict[str, float], templates: list[str]) -> str:
    return build_signature(
        primary_service=incident.primary_service,
        affected=list(incident.affected_services or []),
        signals=signals,
        error_templates=templates,
        root_cause_category=incident.root_cause_category,
        severity=incident.severity,
    )
