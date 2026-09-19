"""``fit-reference``: the only step that looks at a whole cohort.

It measures cohort-dependent constants once and freezes them in
``params/reference_v1.json`` with a sha256. ``predict`` never refits: it loads
the file, refuses a hash mismatch and stamps ``params_hash`` on every row.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .cleaning import CleanTables
from .contracts import DashRule, Params
from .io import DEFAULT_CACHE_DIR
from .params import DEFAULT_PARAMS_PATH


def fit_month_factors(clean: CleanTables, base: Params) -> tuple[float, ...]:
    """January..December factors of operating inflow, normalised to mean 1.

    Median over entities with at least 18 observed months of (month inflow /
    own median monthly inflow), per calendar month.
    """
    raise NotImplementedError


def fit_winsor_limits(panel: pl.DataFrame, base: Params) -> dict[str, tuple[float, float]]:
    """Limits for the keys of ``base.winsor`` from pooled panel quantiles."""
    raise NotImplementedError


def measure_dash_rules(clean: CleanTables, base: Params) -> tuple[DashRule, ...]:
    """Fills ``precision`` and ``support`` of every rule.

    Each rule runs on rows that do have a category; precision is the share of
    matches whose category agrees with the label of the rule.
    """
    raise NotImplementedError


def fit_reference_medians(scores: pl.DataFrame) -> dict[str, float]:
    """B_k: median of every pillar over group rows (``SNAPSHOT_SCHEMA`` frame)."""
    raise NotImplementedError


def fit_psi_bins(
    scores: pl.DataFrame, edges: tuple[float, ...]
) -> dict[str, tuple[float, ...]]:
    """Share of group scores per bin of ``edges``, for every branch."""
    raise NotImplementedError


def fit_reference(
    input_dir: Path,
    out_path: Path = DEFAULT_PARAMS_PATH,
    base: Params | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Params:
    """Two passes over ``input_dir`` starting from ``base`` (default: the
    current params file, hash not verified).

    Pass one: month-of-year factors, winsor limits, dash-rule precision.
    Pass two (scoring with pass-one params): B_k medians and PSI bins.
    Hand-set values (weights, anchors, lam/tau, caps, FX, thresholds) are kept.
    Sets ``fitted``, ``fitted_on`` (dataset hash) and the section flags, writes
    the file with ``params.write_params`` and returns the stamped ``Params``.
    Aggregates only: nothing per company or per group is written.
    """
    raise NotImplementedError
