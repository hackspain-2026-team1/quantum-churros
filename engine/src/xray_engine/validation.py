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
NEUTRALITY_DIMENSIONS: tuple[str, ...] = (
    "size_band", "erp_tier", "main_bank", "calendar_month", "coverage_branch",
)
CHECK_KEYS: tuple[str, ...] = (
    "isolation", "truncation", "additivity", "scale", "determinism", "ablation", "neutrality",
    "penalty_by_branch", "rank_stability", "history_truncation", "persistence",
    "netting_placebo", "injection",
)


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
    """Score and delta identities on every real row, carried months included,
    plus the integer-tenths sum."""
    raise NotImplementedError


def check_scale_invariance(result: ScoreResult, factor: float = 1024.0) -> dict[str, Any]:
    """Re-scores the panel with every EUR column multiplied by ``factor``.

    Pure core only: the mirror gate and the size band are set in EUR on
    purpose, so the panel keeps its ``size_band`` labels.
    """
    raise NotImplementedError


def check_determinism(input_dir: Path, result: ScoreResult) -> dict[str, Any]:
    """Second run and a run on row-shuffled CSVs must give ``frame.equals``."""
    raise NotImplementedError


def paired_ablation(result: ScoreResult) -> dict[str, Any]:
    """Same groups scored with and without the invoice pillars (payments and
    collections set to None on the pillar results, then re-aggregated): mean
    shift of the score and Spearman of the two rankings on the last month.
    Replaces any comparison between populations with and without invoices.
    Also run with the debt pillar removed on debt-bearing groups."""
    raise NotImplementedError


def neutrality(result: ScoreResult) -> dict[str, Any]:
    """Excess eta-squared of the group score over a random partition with the
    same cell sizes, for every one of ``NEUTRALITY_DIMENSIONS``; plus the alert
    rate by calendar month."""
    raise NotImplementedError


def penalty_by_branch(result: ScoreResult) -> dict[str, Any]:
    """Mean penalty and share of months with a penalty, by coverage branch."""
    raise NotImplementedError


def rank_stability(
    result: ScoreResult, *, draws: int = 500, seed: int = 7
) -> dict[str, Any]:
    """Re-aggregates the last month under weight perturbations of +-10 points
    (renormalised) and ``lam`` in [0.3, 0.7]: Spearman of group ranks against
    the baseline and share of groups changing band, overall and by branch."""
    raise NotImplementedError


def history_truncation(
    result: ScoreResult, *, lengths: Sequence[int] = (3, 4, 6, 9, 12)
) -> dict[str, Any]:
    """Groups with the full window re-scored from panels cut to their last k
    months: median absolute score difference against the full history, per k.
    Justifies ``abstention.min_months_observed`` and the history table."""
    raise NotImplementedError


def persistence(result: ScoreResult) -> dict[str, Any]:
    """P(cash + headroom < 0 at t+6 | same at t) against the rate when positive
    at t, group level; same for the score bands."""
    raise NotImplementedError


def netting_placebo(clean: CleanTables, params: Params) -> dict[str, Any]:
    """Mirror recipe re-run with the positive leg shifted 9 to 11 days: pairs
    and outflow value netted by the placebo over the real ones."""
    raise NotImplementedError


def injection_study(
    input_dir: Path, result: ScoreResult, *, seed: int = 7
) -> dict[str, Any]:
    """Injects spikes, steps and ramps into healthy groups, by size band, and
    re-scores only those groups: detection delay distribution,
    P(structural | spike) and the false-alert rate without injection."""
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
    study, uses fewer isolation groups and fewer perturbation draws. Returns
    the written document: ``{dataset_hash, params_hash, engine_version,
    **{key: result for key in CHECK_KEYS}}``.
    """
    raise NotImplementedError
