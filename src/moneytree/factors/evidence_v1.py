"""Stable aggregate evidence contract for research and public publication."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from moneytree.factors.publication import audit_public_snapshot

EVIDENCE_SCHEMA_VERSION = "factor_evidence.v1"


def _section(value: dict[str, Any] | None, *, status: str = "not_provided") -> dict[str, Any]:
    if value is None:
        return {"status": status}
    return dict(value)


def build_factor_evidence_v1(
    snapshot: dict[str, Any],
    *,
    uncertainty: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    residual: dict[str, Any] | None = None,
    temporal_validation: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose aggregate predictive evidence and optional diagnostic sections."""
    audit_public_snapshot(snapshot)
    if snapshot.get("kind") != "moneytree_factor_evidence_snapshot":
        raise ValueError("snapshot must be a moneytree factor evidence snapshot")
    if snapshot.get("schema_version") != "1.0":
        raise ValueError("snapshot schema_version must be 1.0")
    factors = snapshot.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValueError("snapshot factors must be a non-empty list")

    result = {
        "artifact_type": "factor_evidence",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_version": snapshot.get("data_version", "unknown"),
        "dataset": snapshot.get("dataset", {}),
        "predictive": {
            "source_schema": snapshot["schema_version"],
            "factors": factors,
        },
        "uncertainty": _section(uncertainty),
        "risk": _section(risk),
        "residual": _section(residual),
        "temporal_validation": _section(temporal_validation),
        "provenance": _section(provenance),
        "public_limits": [
            "Aggregate evidence only; no ticker-level values or portfolio weights.",
            "Optional sections are explicitly marked not_provided when absent.",
        ],
    }
    audit_public_snapshot(result)
    return result
