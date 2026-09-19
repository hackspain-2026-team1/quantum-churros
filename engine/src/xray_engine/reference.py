"""``fit-reference``: the only step that looks at a whole cohort.

It measures cohort-dependent constants once and freezes them in
``params/reference_v1.json`` with a sha256. ``predict`` never refits: it loads
the file, refuses a hash mismatch and stamps ``params_hash`` on every row.
Fitted here: the liquidity anchor table of each size band, the reference
medians B_k and the measured precision of the narrative rules. Everything
else (weights, domain anchors, lam/tau, caps, bands, FX, thresholds) is
hand-set and kept as it is. No seasonal factors, no score bins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from .cleaning import CleanTables
from .contracts import Anchors, DashRule, Params
from .io import DEFAULT_CACHE_DIR
from .params import DEFAULT_PARAMS_PATH

# A band with fewer group-months keeps its previous table.
MIN_BAND_OBSERVATIONS = 30


def fit_liquidity_band_anchors(panel: pl.DataFrame, base: Params) -> dict[str, Anchors]:
    """One table per size band from the buffer days of group rows.

    Buffer days at month end, computed as ``pillars.pillar_liquidity`` does, on
    group-months with a live feed and a defined buffer. Per band the x-values
    are the ``liquidity.band_quantiles`` of buffer days (made strictly
    increasing and positive), mapped to ``liquidity.band_scores``, after the
    point (0, 0). A band with fewer than ``MIN_BAND_OBSERVATIONS`` group-months
    keeps the table of ``base``.
    """
    raise NotImplementedError


def measure_dash_rules(clean: CleanTables, base: Params) -> tuple[DashRule, ...]:
    """Refreshes ``precision`` and ``support`` of every rule.

    Each rule runs on rows that do have a category; ``support`` is the number
    of matches and ``precision`` the share of them whose category agrees with
    the ``label`` of the rule. Rules without a comparable category
    (``balance_adjustment``) keep None.
    """
    raise NotImplementedError


def fit_reference_medians(scores: pl.DataFrame) -> dict[str, float]:
    """B_k: median of every pillar over live group rows (``SNAPSHOT_SCHEMA`` frame)."""
    raise NotImplementedError


def check_anchor_calibration(scores: pl.DataFrame, base: Params) -> dict[str, Any]:
    """Distribution of every pillar over live group rows against its table:
    quantiles, share at 0 and at 100, share unavailable. Reported, never
    applied: domain anchors are not refitted."""
    raise NotImplementedError


def fit_reference(
    input_dir: Path,
    out_path: Path = DEFAULT_PARAMS_PATH,
    base: Params | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Params:
    """Two passes over ``input_dir`` starting from ``base`` (default: the
    current params file, hash not verified).

    Pass one: narrative-rule precision and the liquidity band tables (the
    panel does not depend on either). Pass two (scoring with pass-one params):
    B_k medians. Hand-set values are kept. Sets ``fitted``, ``fitted_on``
    (dataset hash), ``liquidity.band_anchors_fitted`` and ``reference.fitted``,
    writes the file with ``params.write_params`` and returns the stamped
    ``Params``. Aggregates only: nothing per company or per group is written.
    """
    raise NotImplementedError
