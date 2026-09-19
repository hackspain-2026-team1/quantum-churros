"""``fit-reference``: the only step that looks at a whole cohort.

It measures cohort-dependent constants once and freezes them in
``params/reference_v1.json`` with a sha256. ``predict`` never refits: it loads
the file, refuses a hash mismatch and stamps ``params_hash`` on every row.
Fitted here: the liquidity anchor table of each size band, the reference
medians B_k and the measured precision of the narrative rules. Everything
else (weights, domain anchors, lam/tau, caps, bands, FX, thresholds) is
hand-set and kept as it is. No seasonal factors, no score bins.

The calibration review (``check_anchor_calibration``) only reports where the
cohort lands on the hand-set tables; it never moves an anchor.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import polars as pl

from . import cleaning, io, panel as panel_module, scoring
from .aggregate import live_feed
from .cleaning import CleanTables
from .contracts import PILLAR_KEYS, SIZE_BANDS, Anchors, DashRule, Params
from .io import DEFAULT_CACHE_DIR
from .params import DEFAULT_PARAMS_PATH, load_params, write_params
from .pillars import pillar_liquidity

# A size band with fewer live group-months is pooled with a neighbour.
MIN_BAND_OBSERVATIONS = 150
# Fitted x-values are positive and at least this far apart (anchors must increase).
MIN_ANCHOR_STEP_DAYS = 1.0
REVIEW_QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)
# Acceptance of a hand-set table: where the median lands, and how much saturates.
REVIEW_MEDIAN_RANGE: tuple[float, float] = (50.0, 75.0)
REVIEW_MAX_SATURATED = 0.20
# Hand-set tables under review: anchors key -> (pillar, raw metric in the snapshot series).
REVIEWED_TABLES: dict[str, tuple[str, str]] = {
    "activity_coverage": ("activity", "activity_coverage"),
    "activity_momentum": ("activity", "activity_momentum"),
    "debt_burden": ("debt", "debt_burden"),
}


def quantile(values: list[float], q: float) -> float:
    """Linear-interpolation quantile of ``values`` sorted ascending."""
    if not values:
        raise ValueError("quantile of an empty sample")
    position = q * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def band_observations(panel: pl.DataFrame, base: Params) -> dict[str, list[float]]:
    """Buffer days at month end per size band, sorted ascending.

    Group rows with a live feed, a known size band and a defined buffer,
    computed exactly as ``pillars.pillar_liquidity`` does."""
    found: dict[str, list[float]] = {band: [] for band in SIZE_BANDS}
    groups = panel.filter(pl.col("entity_kind") == "group")
    for row in panel_module.iter_rows(groups):
        if row.size_band not in found or not live_feed(row, base):
            continue
        days = pillar_liquidity(row, base).inputs.get("buffer_days_month_end")
        if days is not None:
            found[row.size_band].append(days)
    return {band: sorted(values) for band, values in found.items()}


def band_pools(counts: dict[str, int], minimum: int = MIN_BAND_OBSERVATIONS) -> dict[str, tuple[str, ...]]:
    """Bands fitted together: band -> the adjacent bands pooled with it (itself included).

    While a pool holds fewer than ``minimum`` observations it joins its thinner
    neighbour (the lower one on a tie), so every table rests on enough rows."""
    pools: list[list[str]] = [[band] for band in SIZE_BANDS]
    size = lambda pool: sum(counts.get(band, 0) for band in pool)  # noqa: E731
    while len(pools) > 1:
        thin = [index for index, pool in enumerate(pools) if size(pool) < minimum]
        if not thin:
            break
        index = min(thin, key=lambda item: (size(pools[item]), item))
        sides = [side for side in (index - 1, index + 1) if 0 <= side < len(pools)]
        other = min(sides, key=lambda side: (size(pools[side]), side))
        low, high = sorted((index, other))
        pools[low:high + 1] = [pools[low] + pools[high]]
    return {band: tuple(pool) for pool in pools for band in pool}


def _band_table(values: list[float], base: Params) -> Anchors:
    points = [(0.0, 0.0)]
    for q, score in zip(base.liquidity.band_quantiles, base.liquidity.band_scores):
        x = max(round(quantile(values, q), 2), points[-1][0] + MIN_ANCHOR_STEP_DAYS)
        points.append((x, score))
    return Anchors(tuple(points))


def _fit_bands(panel: pl.DataFrame, base: Params) -> tuple[dict[str, Anchors], dict[str, Any]]:
    observations = band_observations(panel, base)
    counts = {band: len(values) for band, values in observations.items()}
    pools = band_pools(counts)
    tables: dict[str, Anchors] = {}
    report: dict[str, Any] = {}
    for band in SIZE_BANDS:
        pooled = sorted(value for member in pools[band] for value in observations[member])
        fitted = len(pooled) >= MIN_BAND_OBSERVATIONS
        tables[band] = _band_table(pooled, base) if fitted else base.liquidity.band_anchors[band]
        report[band] = {
            "group_months": counts[band],
            "pooled_with": [member for member in pools[band] if member != band],
            "pooled_group_months": len(pooled),
            "fitted": fitted,
            "quantiles_days": (
                {f"p{round(q * 100)}": round(quantile(pooled, q), 2) for q in base.liquidity.band_quantiles}
                if pooled else {}
            ),
            "anchors": [list(point) for point in tables[band].points],
        }
    return tables, report


def fit_liquidity_band_anchors(panel: pl.DataFrame, base: Params) -> dict[str, Anchors]:
    """One table per size band from the buffer days of group rows.

    Buffer days at month end, computed as ``pillars.pillar_liquidity`` does, on
    group-months with a live feed and a defined buffer. Per band the x-values
    are the ``liquidity.band_quantiles`` of buffer days (rounded to 0.01 day,
    made positive and at least ``MIN_ANCHOR_STEP_DAYS`` apart), mapped to
    ``liquidity.band_scores``, after the point (0, 0). A band with fewer than
    ``MIN_BAND_OBSERVATIONS`` group-months is pooled with its thinner neighbour
    (``band_pools``) and both read the pooled table; if even the pool of every
    band is too small the tables of ``base`` are kept.
    """
    return _fit_bands(panel, base)[0]


def measure_dash_rules(clean: CleanTables, base: Params) -> tuple[DashRule, ...]:
    """Refreshes ``precision`` and ``support`` of every rule.

    Each rule runs, as ``cleaning.classify_flows`` applies it (pattern, veto
    and sign), on the booked in-window rows that do have a category;
    ``support`` is the number of matches and ``precision`` the share of them
    whose category equals the ``label`` of the rule. Rules without a comparable
    category (``balance_adjustment``) and rules without a match keep their
    previous values.
    """
    categories = set(base.flows.op_inflow_categories) | set(base.flows.op_outflow_categories)
    categories |= set(base.flows.debt_service_categories) | set(base.flows.internal_categories)
    window = clean.window
    cents, category = pl.col("amount_cents"), pl.col("category")
    rows = clean.transactions.filter(
        (category.str.len_bytes() > 0)
        & (category != base.flows.dash_category)
        & (cents != 0)
        & pl.col("month").is_between(window.first_month, window.last_month)
    ).select(
        "amount_cents", "category",
        pl.col("description").fill_null("").str.replace_all(r"\s+", " ").str.strip_chars().alias("text"),
    )
    measured = []
    for rule in base.dash_rules:
        if rule.label not in categories:
            measured.append(rule)
            continue
        hit = pl.col("text").str.contains(f"(?i:{rule.pattern})")
        if rule.exclude:
            hit = hit & ~pl.col("text").str.contains(f"(?i:{rule.exclude})")
        if rule.sign != "any":
            hit = hit & ((cents < 0) if rule.sign == "negative" else (cents > 0))
        counts = rows.select(
            hit.sum().alias("support"), (hit & (category == rule.label)).sum().alias("agree")
        ).row(0)
        support, agree = int(counts[0]), int(counts[1])
        if support == 0:
            measured.append(rule)
        else:
            measured.append(replace(rule, precision=round(agree / support, 3), support=support))
    return tuple(measured)


def _live_groups(scores: pl.DataFrame) -> pl.DataFrame:
    return scores.filter((pl.col("entity_kind") == "group") & pl.col("feed_live"))


def fit_reference_medians(scores: pl.DataFrame) -> dict[str, float]:
    """B_k: median of every pillar over live group rows (``SNAPSHOT_SCHEMA``
    frame), rounded to 0.01. A pillar nobody has is left out."""
    live = _live_groups(scores)
    medians: dict[str, float] = {}
    for key in PILLAR_KEYS:
        values = sorted(live["pillars"].struct.field(key).drop_nulls().to_list())
        if values:
            medians[key] = round(quantile(values, 0.5), 2)
    return medians


def _spread(values: list[float]) -> dict[str, float]:
    return {f"p{round(q * 100)}": round(quantile(values, q), 4) for q in REVIEW_QUANTILES}


def check_anchor_calibration(scores: pl.DataFrame, base: Params) -> dict[str, Any]:
    """Where the cohort lands on the tables. Reported, never applied.

    Over live group rows. ``pillars``: per pillar the quantiles of the score,
    the share at 0 and at 100 and the share unavailable. ``tables``: per
    hand-set table of ``REVIEWED_TABLES`` the quantiles of the raw metric, the
    score each one maps to, the share of rows the table sends to 0 and to 100
    and ``acceptable``: the median maps inside ``REVIEW_MEDIAN_RANGE`` and at
    most ``REVIEW_MAX_SATURATED`` of the rows saturate (both ends together).
    """
    live = _live_groups(scores)
    total = live.height
    pillars: dict[str, Any] = {}
    for key in PILLAR_KEYS:
        values = sorted(live["pillars"].struct.field(key).drop_nulls().to_list())
        pillars[key] = {
            "group_months": len(values),
            "unavailable_share": round(1 - len(values) / total, 4) if total else None,
            "quantiles": _spread(values) if values else {},
            "at_0_share": round(sum(value <= 0.0 for value in values) / len(values), 4) if values else None,
            "at_100_share": round(sum(value >= 100.0 for value in values) / len(values), 4) if values else None,
        }
    tables: dict[str, Any] = {}
    low, high = REVIEW_MEDIAN_RANGE
    for name, (_, metric) in REVIEWED_TABLES.items():
        table = base.anchors[name]
        values = sorted(live["series"].struct.field(metric).drop_nulls().to_list())
        if not values:
            tables[name] = {"group_months": 0, "acceptable": None}
            continue
        mapped = [table(value) for value in values]
        at_0 = sum(score <= 0.0 for score in mapped) / len(mapped)
        at_100 = sum(score >= 100.0 for score in mapped) / len(mapped)
        raw = _spread(values)
        median_score = table(quantile(values, 0.5))
        tables[name] = {
            "group_months": len(values),
            "anchors": [list(point) for point in table.points],
            "raw_quantiles": raw,
            "score_at_quantiles": {label: round(table(value), 2) for label, value in raw.items()},
            "at_0_share": round(at_0, 4),
            "at_100_share": round(at_100, 4),
            "median_score": round(median_score, 2),
            "acceptable": bool(low <= median_score <= high and at_0 + at_100 <= REVIEW_MAX_SATURATED),
        }
    return {"group_months": total, "pillars": pillars, "tables": tables}


def fit_reference(
    input_dir: Path,
    out_path: Path = DEFAULT_PARAMS_PATH,
    base: Params | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    *,
    report_path: Path | None = None,
) -> Params:
    """Two passes over ``input_dir`` starting from ``base`` (default: the
    current params file, hash not verified).

    Pass one: narrative-rule precision and the liquidity band tables (the
    panel does not depend on either). Pass two (scoring with pass-one params):
    B_k medians. Hand-set values are kept. Sets ``fitted``, ``fitted_on``
    (dataset hash), ``liquidity.band_anchors_fitted`` and ``reference.fitted``,
    writes the file with ``params.write_params`` and returns the stamped
    ``Params``. Aggregates only: nothing per company or per group is written.
    ``report_path`` receives the fit report as JSON (band counts and pools,
    rule precision, medians and the calibration review).
    """
    base = base if base is not None else load_params(out_path if Path(out_path).is_file() else None, verify=False)
    tables = io.load_source(input_dir, cache_dir)
    clean = cleaning.clean(tables, base)
    panel = panel_module.build_panel(clean, base)

    rules = measure_dash_rules(clean, base)
    band_tables, band_report = _fit_bands(panel, base)
    bands_fitted = any(item["fitted"] for item in band_report.values())
    first = replace(
        base,
        dash_rules=rules,
        liquidity=replace(base.liquidity, band_anchors=band_tables, band_anchors_fitted=bands_fitted),
    )

    scores = scoring.score_frame(scoring.score_panel(panel, first), first, tables.dataset_hash)
    medians = {**base.reference.medians, **fit_reference_medians(scores)}
    fitted = replace(
        first,
        fitted=True,
        fitted_on=tables.dataset_hash,
        reference=replace(first.reference, medians=medians, fitted=True),
    )
    stamped = write_params(fitted, Path(out_path))
    if report_path is not None:
        report = {
            "dataset_hash": tables.dataset_hash,
            "params_hash": stamped.sha256,
            "window": [tables.window.first_month.isoformat(), tables.window.last_month.isoformat()],
            "min_band_observations": MIN_BAND_OBSERVATIONS,
            "liquidity_bands": band_report,
            "reference_medians": medians,
            "dash_rules": {
                rule.id: {"label": rule.label, "precision": rule.precision, "support": rule.support}
                for rule in rules
            },
            "calibration": check_anchor_calibration(scores, stamped),
        }
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return stamped


__all__ = [
    "MIN_BAND_OBSERVATIONS",
    "REVIEWED_TABLES",
    "band_observations",
    "band_pools",
    "check_anchor_calibration",
    "fit_liquidity_band_anchors",
    "fit_reference",
    "fit_reference_medians",
    "measure_dash_rules",
    "quantile",
]
