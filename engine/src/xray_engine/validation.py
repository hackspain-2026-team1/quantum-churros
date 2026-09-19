"""Label-free validation: the receipt behind every published score.

Each check returns a plain dict with at least ``{"pass": bool | None}`` plus
its own measurements (aggregates only). ``run_validation`` collects them in
``validation.json``; the bundle receipt is built from that file.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from .cleaning import CleanTables
from .contracts import Params
from .io import DEFAULT_CACHE_DIR
from .scoring import ScoreResult

DEFAULT_VALIDATION_PATH = Path("artifacts/validation.json")
TRUNCATION_MONTHS: tuple[str, ...] = ("2025-08", "2026-02", "2026-05")


def compare_scores(
    left: pl.DataFrame, right: pl.DataFrame, tol: float = 1e-9
) -> dict[str, Any]:
    """Joins two ``SNAPSHOT_SCHEMA`` frames on (entity_kind, entity_id, month).

    Returns ``{n, missing_left, missing_right, max_abs_diff, categorical_mismatches,
    tol, pass}``: numeric columns (struct fields included) within ``tol``,
    every other column equal. ``dataset_hash`` is ignored.
    """
    raise NotImplementedError


def check_isolation(
    input_dir: Path,
    result: ScoreResult,
    *,
    n_groups: int = 60,
    seed: int = 7,
    tol: float = 1e-9,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Scores ``n_groups`` groups alone and compares with the full ``result``.

    Groups are drawn with ``seed``, stratified by size and invoice coverage;
    the eight CSVs are filtered at file level into ``work_dir``.
    """
    raise NotImplementedError


def check_truncation(
    input_dir: Path,
    result: ScoreResult,
    *,
    months: Sequence[str] = TRUNCATION_MONTHS,
    tol: float = 1e-9,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """For every t: cut transactions and invoices at the end of t, re-open
    invoices settled later, roll balances back in cents (sentinels untouched),
    score, and require the rows with month <= t to equal those of ``result``."""
    raise NotImplementedError


def check_additivity(result: ScoreResult, tol: float = 1e-9) -> dict[str, Any]:
    """Score and delta identities on every real row, plus the integer-tenths sum."""
    raise NotImplementedError


def check_scale_invariance(result: ScoreResult, factor: float = 1024.0) -> dict[str, Any]:
    """Re-scores the panel with every EUR column multiplied by ``factor``."""
    raise NotImplementedError


def check_determinism(input_dir: Path, result: ScoreResult) -> dict[str, Any]:
    """Second run and a run on row-shuffled CSVs must give ``frame.equals``."""
    raise NotImplementedError


def branch_parity_psi(result: ScoreResult) -> dict[str, Any]:
    """PSI of group scores between branches with and without invoices (< 0.1)."""
    raise NotImplementedError


def neutrality(result: ScoreResult) -> dict[str, Any]:
    """Score level and alert rate by size band and by months since connection."""
    raise NotImplementedError


def persistence(result: ScoreResult) -> dict[str, Any]:
    """P(state at t+6 | state at t) against the base rate, for level states."""
    raise NotImplementedError


def netting_placebo(clean: CleanTables, params: Params) -> dict[str, Any]:
    """Mirror pairs found across different groups (placebo) over real pairs."""
    raise NotImplementedError


def injection_study(
    input_dir: Path, result: ScoreResult, *, seed: int = 7
) -> dict[str, Any]:
    """Injects controlled deteriorations into healthy groups and re-scores only
    those groups: detection delay distribution, false alerts, bump vs fall."""
    raise NotImplementedError


def run_validation(
    input_dir: Path,
    params: Params | None = None,
    out_path: Path = DEFAULT_VALIDATION_PATH,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    quick: bool = False,
) -> dict[str, Any]:
    """Runs every check and writes ``out_path``. ``quick`` skips the injection
    study and uses fewer isolation groups. Returns the written document:
    ``{dataset_hash, params_hash, engine_version, isolation, truncation,
    additivity, scale, determinism, branch_parity, neutrality, persistence,
    netting_placebo, injection}``.
    """
    raise NotImplementedError
