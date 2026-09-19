"""Append a KPI history row from ``validation.json`` (etiquetas legibles)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .eval_labels import KPI_HISTORY_COLUMNS


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _history_header() -> str:
    short_headers = [col[0] for col in KPI_HISTORY_COLUMNS]
    lines = [
        "# Historial de evaluación — Fase A",
        "",
        "Una fila por `make eval-phase-a`. No editar a mano las filas generadas.",
        "",
        "## Qué mide cada columna",
        "",
        "| Columna | Qué se está probando |",
        "| --- | --- |",
    ]
    for key, description in KPI_HISTORY_COLUMNS:
        if key in ("fecha", "dataset", "params", "motor", "runtime"):
            continue
        lines.append(f"| {key} | {description} |")
    lines.extend([
        "",
        "| " + " | ".join(short_headers) + " |",
        "| " + " | ".join("---" for _ in short_headers) + " |",
    ])
    return "\n".join(lines) + "\n"


def format_snapshot_row(document: Mapping[str, Any], *, run_at: datetime | None = None) -> str:
    """One markdown table row for ``docs/engine/KPI_HISTORY.md``."""
    when = (run_at or datetime.now(tz=UTC)).strftime("%Y-%m-%d %H:%M UTC")
    kpis = document.get("kpis") or {}
    stages = kpis.get("by_stage") or {}
    reconcile = stages.get("reconcile") or {}
    normalize = stages.get("normalize") or {}
    score = stages.get("score") or {}
    cells = [
        when,
        str(document.get("dataset_hash", "—")),
        str(document.get("params_hash", "—")),
        str(document.get("engine_version", "—")),
        _fmt(reconcile.get("netting_placebo_pass")),
        _fmt(normalize.get("truncation_pass")),
        _fmt(normalize.get("scale_pass")),
        _fmt(normalize.get("coverage_scored_pct")),
        _fmt(score.get("holdout_n_groups")),
        _fmt(score.get("level_autocorr_lag3")),
        _fmt(score.get("slope_autocorr_lag3")),
        _fmt(score.get("rolling_min_spearman")),
        _fmt(score.get("p_structural_given_spike")),
        f"{document.get('runtime_seconds', '—')}s",
    ]
    formatted = [f"`{cell}`" if index in (1, 2) else str(cell) for index, cell in enumerate(cells)]
    return "| " + " | ".join(formatted) + " |"


def _legacy_header(text: str) -> bool:
    """True when the file still uses acronyms (R6, P2, …) instead of readable labels."""
    first_line = text.splitlines()[0] if text else ""
    return "KPI history" in first_line or "| R6 |" in text or "| P2 |" in text


def _data_rows(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.startswith("|") and "---" not in line and "Columna" not in line
        and not line.startswith("| fecha |")
        and not line.startswith("| Fecha |")
    ]


def append_kpi_history(
    validation_path: Path,
    history_path: Path,
    *,
    run_at: datetime | None = None,
) -> str:
    """Append one row to ``history_path``; create or refresh header if outdated."""
    document = json.loads(Path(validation_path).read_text(encoding="utf-8"))
    row = format_snapshot_row(document, run_at=run_at)
    history_path = Path(history_path)
    header = _history_header()
    if not history_path.exists():
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(header + row + "\n", encoding="utf-8")
        return row
    text = history_path.read_text(encoding="utf-8")
    if "Qué mide cada columna" not in text or _legacy_header(text):
        preserved = [line for line in _data_rows(text) if line != row]
        history_path.write_text(header + "\n".join(preserved + [row]) + "\n", encoding="utf-8")
        return row
    if row in text:
        return row
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")
    return row


__all__ = ["append_kpi_history", "format_snapshot_row"]
