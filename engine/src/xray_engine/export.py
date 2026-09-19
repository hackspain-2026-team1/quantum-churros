"""Static JSON bundle for the web app (contract ``contracts/xray-export-v1.schema.json``).

Files: ``manifest.json``, ``portfolio.json``, ``groups/<id>.json``,
``companies/<id>.json``, ``evidence/<id>.json``, ``alerts.json``,
``receipt.json``. Every number comes from a ``ScoreResult``; evidence rows are
aggregates, never raw descriptions. Output is byte-identical for identical
inputs: sorted keys, fixed separators, no wall-clock values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .scoring import ScoreResult

BUNDLE_SCHEMA = "xray-export-v1"


def round_preserving_sum(
    parts: Sequence[float], total: float, scale: int = 10
) -> list[int]:
    """Largest-remainder rounding of signed ``parts`` to integers of ``1/scale``.

    Returns integers ``r`` with ``sum(r) == round(total * scale)`` and
    ``|r[i] - parts[i] * scale| < 1``: each part is floored, then the missing
    units go to the largest fractional remainders (ties: lowest index).
    Expects ``sum(parts) == total`` up to float noise. With parts ``[base,
    *contributions, -penalty, -cap_adjustment]`` and ``total = score`` the
    on-screen sum is exact in integer tenths.
    """
    raise NotImplementedError


def export_bundle(
    result: ScoreResult,
    out_dir: Path,
    *,
    evidence_months: int = 24,
    receipt: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Writes the bundle under ``out_dir`` and returns the manifest.

    ``manifest``: schema, bundle_id (sha256 of the other files, sorted by
    path), engine_version, params_hash, dataset_hash, generated_at, months.
    ``generated_at`` defaults to ``result.window.as_of`` so that two runs give
    the same bytes. ``evidence_months`` limits ``evidence/<id>.json`` to the
    last months. ``receipt`` is the output of ``validation.run_validation``;
    without it ``receipt.json`` holds only the sections derivable from
    ``result`` (signals and weights, abstentions). Contributions are emitted in
    integer tenths through ``round_preserving_sum``.
    """
    raise NotImplementedError
