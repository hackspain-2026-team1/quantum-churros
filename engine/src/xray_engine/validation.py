"""Label-free validation: the receipt behind every published score.

``run_validation`` loads the tables once, scores them once (``Scored``) and
every check reuses that result. Checks that need another run (isolation,
truncation, determinism, history truncation) filter or cut the tables already
in memory; checks on the aggregation (ablation, rank stability, injection) go
through the pure core only. Each check returns a plain dict with ``pass``
(True | False | None), a Spanish ``summary``, ``metrics`` ready for the bundle
receipt and its raw measurements (aggregates only).
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import polars as pl

from . import cleaning, io, panel as panel_module
from .aggregate import aggregate, delta_parts
from .alerts import build_alerts
from .cleaning import CleanTables
from .contracts import (
    ENGINE_VERSION,
    PANEL_MONEY_COLUMNS,
    PILLAR_KEYS,
    PILLAR_LABELS,
    UNLOCK_HINTS,
    Alert,
    EntityMonth,
    PanelRow,
    Params,
    PillarResult,
    band_of,
)
from .io import DEFAULT_CACHE_DIR
from .params import load_params
from .scoring import score_entity, score_panel

DEFAULT_VALIDATION_PATH = Path("artifacts/validation.json")
BUNDLE_SCHEMA = "xray-export-v1"
TRUNCATION_OFFSETS: tuple[int, ...] = (12, 6, 3)  # months before the last one
NEUTRALITY_DIMENSIONS: tuple[str, ...] = (
    "size_band", "erp_tier", "main_bank", "calendar_month", "coverage_branch",
)
NEUTRALITY_OK = 0.03
NEUTRALITY_FAIL = 0.10
CHECK_KEYS: tuple[str, ...] = (
    "isolation", "truncation", "additivity", "scale", "determinism", "ablation", "neutrality",
    "penalty_by_branch", "rank_stability", "history_truncation", "persistence",
    "netting_placebo", "injection",
)
# expensive checks left out by ``quick``
QUICK_SKIPPED: tuple[str, ...] = ("history_truncation", "netting_placebo", "injection")
INJECTION_KINDS: tuple[str, ...] = ("spike", "step", "ramp")
P_STRUCTURAL_SPIKE_MAX = 0.10
P_STRUCTURAL_STEP_MIN = 0.70

TITLES: dict[str, str] = {
    "isolation": "Aislamiento de cohorte",
    "truncation": "Sin mirar al futuro",
    "additivity": "Identidad aditiva",
    "scale": "Invarianza de escala",
    "determinism": "Determinismo",
    "ablation": "Ablación pareada",
    "neutrality": "Neutralidad",
    "penalty_by_branch": "Penalización por rama",
    "rank_stability": "Estabilidad del orden",
    "history_truncation": "Historia mínima",
    "persistence": "Persistencia",
    "netting_placebo": "Placebo de traspasos",
    "injection": "Deterioros inyectados",
}
NOT_RUN = "Comprobación no ejecutada en esta validación."
SNAPSHOT_EXCEPTIONS: tuple[str, ...] = (
    "saldo ancla retrocedido en céntimos hasta el corte",
    "límites concedidos leídos de la foto actual (se suponen constantes)",
    "lista de productos de deuda leída de la foto actual",
)
# fallbacks when export.py cannot be imported
_SIGNAL_WHY = "Pilar del score con su peso nominal."
_ZERO_WEIGHT = (
    ("industry", "Sector inferido", "Contexto de la ficha: no entra en el número."),
    ("customer_concentration", "Concentración de clientes", "Rasgo del negocio: ni pilar ni alerta."),
    ("seasonality", "Estacionalidad", "No se distingue del ruido con dos años de historia."),
)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_KEYS = ["entity_kind", "entity_id", "month"]


# --------------------------------------------------------------------------
# the one scored result
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scored:
    """One run of the engine, kept whole so every check reuses it."""

    tables: io.Tables
    clean: CleanTables
    panel: pl.DataFrame
    months: tuple[EntityMonth, ...]
    frame: pl.DataFrame  # ``core_frame`` of ``months``
    alerts: tuple[Alert, ...]
    params: Params

    @property
    def last_month(self) -> date:
        return self.tables.window.last_month


def _entities(months: Sequence[EntityMonth]) -> dict[tuple[str, str], list[EntityMonth]]:
    found: dict[tuple[str, str], list[EntityMonth]] = defaultdict(list)
    for item in months:
        found[(item.row.entity_kind, item.row.entity_id)].append(item)
    return {key: sorted(found[key], key=lambda item: item.row.month) for key in sorted(found)}


def _groups(scored: Scored) -> dict[str, list[EntityMonth]]:
    return {key[1]: items for key, items in _entities(scored.months).items() if key[0] == "group"}


def _joined(values: Any) -> str:
    return "|".join(str(item) for item in (values or ()))


def core_frame(months: Sequence[EntityMonth]) -> pl.DataFrame:
    """Every number and label of ``ScoreParts`` and of the verdict, one row per
    entity-month, flat. Optional fields missing on a result read as null."""
    records = []
    for item in months:
        row, parts, verdict = item.row, item.parts, item.trajectory
        record: dict[str, Any] = {
            "entity_kind": row.entity_kind, "entity_id": row.entity_id, "group_id": row.group_id,
            "month": row.month, "months_observed": row.months_observed,
            "score": parts.score, "level": parts.level, "level_weighted": parts.level_weighted,
            "base": parts.base, "penalty": parts.penalty, "cap_adjustment": parts.cap_adjustment,
            "confidence": parts.confidence,
            "band": parts.band, "size_band": getattr(parts, "size_band", None), "branch": parts.branch,
            "feed_live": parts.feed_live, "carried_from": parts.carried_from,
            "confidence_label": parts.confidence_label, "abstained": parts.abstained,
            "abstain_reason": parts.abstain_reason, "caps_fired": _joined(parts.caps_fired),
            "flags": _joined(parts.flags),
            "direction": getattr(verdict, "direction", None), "nature": getattr(verdict, "nature", None),
            "horizon": getattr(verdict, "horizon", None),
            "shock_pending": getattr(verdict, "shock_pending", None),
            "delta3": getattr(verdict, "delta3", None), "drift_points": getattr(verdict, "drift_points", None),
        }
        for key in PILLAR_KEYS:
            record[f"p_{key}"] = parts.pillar_scores.get(key)
            record[f"w_{key}"] = parts.weights_effective.get(key)
            record[f"c_{key}"] = parts.contributions.get(key)
            record[f"gates_{key}"] = _joined(item.pillars[key].gates) if key in item.pillars else ""
        records.append(record)
    floats = ("score", "level", "level_weighted", "base", "penalty", "cap_adjustment", "confidence",
              "delta3", "drift_points", *(f"{prefix}_{key}" for key in PILLAR_KEYS for prefix in "pwc"))
    schema: dict[str, Any] = {
        "entity_kind": pl.String, "entity_id": pl.String, "group_id": pl.String, "month": pl.Date,
        "months_observed": pl.Int64, "feed_live": pl.Boolean, "carried_from": pl.Date,
        "abstained": pl.Boolean, "shock_pending": pl.Boolean,
    }
    names = list(records[0]) if records else [*schema, *floats]
    full = {name: schema.get(name, pl.Float64 if name in floats else pl.String) for name in names}
    return pl.DataFrame(records, schema=full).sort(_KEYS)


def score_core(tables: io.Tables, params: Params) -> Scored:
    """clean -> panel -> pure core -> alerts. No profile cards, no bundle."""
    clean = cleaning.clean(tables, params)
    panel = panel_module.build_panel(clean, params)
    months = score_panel(panel, params)
    alerts: list[Alert] = []
    for items in _entities(months).values():
        alerts.extend(build_alerts(items, params))
    return Scored(tables, clean, panel, tuple(months), core_frame(months), tuple(alerts), params)


# --------------------------------------------------------------------------
# tables in memory: subset, cut, shuffle
# --------------------------------------------------------------------------


def _month_end(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _shift_month(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def subset_tables(tables: io.Tables, group_ids: Sequence[str]) -> io.Tables:
    """The same extraction holding only ``group_ids`` (every table filtered)."""
    keep = list(group_ids)
    companies = tables.companies.filter(pl.col("group_id").is_in(keep))
    members = companies["company_id"].to_list()
    own = pl.col("company_id").is_in(members)
    return replace(
        tables,
        groups=tables.groups.filter(pl.col("group_id").is_in(keep)),
        companies=companies,
        banking_products=tables.banking_products.filter(own),
        debt_products=tables.debt_products.filter(own),
        debt_schedule_config=tables.debt_schedule_config.filter(own),
        transactions=tables.transactions.filter(own),
        invoices=tables.invoices.filter(own),
        balances=tables.balances.filter(own),
    )


def roll_balances(tables: io.Tables, cut: date, params: Params) -> tuple[pl.DataFrame, list[str]]:
    """Balance rows as read on ``cut``: per product the latest real reading
    after the cut, rolled back in cents through the booked rows in between and
    dated at the cut; sentinel readings keep their value. Also returns the
    products whose rolled balance reaches the sentinel magnitude: a reading the
    engine would have dropped on that day."""
    balances = tables.balances
    after = balances.filter(pl.col("date") > cut)
    if after.is_empty():
        return balances, []
    sentinel = pl.col("balance_cents").abs() / 100 >= params.flows.sentinel_abs_balance
    placeholders = after.filter(sentinel).with_columns(pl.lit(cut).cast(pl.Date).alias("date"))
    real = (
        after.filter(~sentinel.fill_null(False)).sort("product_id", "date")
        .group_by("product_id", maintain_order=True).last()
    )
    moved = (
        real.select("product_id", pl.col("date").alias("anchor"))
        .join(tables.transactions.filter(pl.col("date") > cut).select("product_id", "date", "amount_cents"), on="product_id")
        .filter(pl.col("date") <= pl.col("anchor"))
        .group_by("product_id")
        .agg(pl.col("amount_cents").sum().alias("moved"))
    )
    rolled = real.join(moved, on="product_id", how="left").with_columns(pl.col("moved").fill_null(0))
    rolled = rolled.with_columns(
        [(pl.col(name) - pl.col("moved")).alias(name)
         for name in ("balance_cents", "liquidity_cents", "countable_cents") if name in rolled.columns]
        + [pl.lit(cut).cast(pl.Date).alias("date")]
    ).select(balances.columns)
    crossers = rolled.filter(sentinel)["product_id"].to_list()
    # a reading at the cut itself is replaced by the rolled one
    kept = balances.filter(pl.col("date") <= cut).join(
        rolled.select("product_id", "date"), on=["product_id", "date"], how="anti"
    )
    return pl.concat([kept, rolled, placeholders.select(balances.columns)]).sort("product_id", "date"), sorted(crossers)


def truncate_tables(tables: io.Tables, last_month: date, params: Params) -> io.Tables:
    """The tables as extracted at the end of ``last_month``.

    Later transactions and invoices are removed, invoices settled later are
    re-opened, and balance rows read after the cut are rolled back in integer
    cents and dated at the cut (sentinels keep their value). Master data and
    the debt stock stay as declared: the snapshot exceptions.
    """
    cut = _month_end(last_month)
    transactions = tables.transactions.filter(pl.col("date") <= cut)
    late = (pl.col("status") == "paid") & (pl.col("payment_date") > cut)
    invoices = tables.invoices.filter(pl.col("issuance_date").is_null() | (pl.col("issuance_date") <= cut))
    invoices = invoices.with_columns(
        pl.when(late).then(pl.when(pl.col("due_date") <= cut).then(pl.lit("overdue")).otherwise(pl.lit("pending")))
        .otherwise(pl.col("status")).alias("status"),
        pl.when(late).then(pl.col("amount_cents")).otherwise(pl.col("pending_cents")).alias("pending_cents"),
        pl.when(late).then(pl.col("due_date")).otherwise(pl.col("payment_date")).alias("payment_date"),
    )
    balances, _ = roll_balances(tables, cut, params)
    first = transactions["month"].min() or tables.window.first_month
    window = io.Window(first_month=first, last_month=last_month, as_of=cut)
    return replace(tables, transactions=transactions, invoices=invoices, balances=balances, window=window)


def tail_tables(tables: io.Tables, group_ids: Sequence[str], first_month: date) -> io.Tables:
    """``group_ids`` as if connected on ``first_month``: earlier transactions
    and invoices issued earlier are not visible."""
    sub = subset_tables(tables, group_ids)
    transactions = sub.transactions.filter(pl.col("month") >= first_month)
    invoices = sub.invoices.filter(pl.col("issuance_date") >= first_month)
    start = transactions["month"].min() or first_month
    return replace(sub, transactions=transactions, invoices=invoices, window=replace(sub.window, first_month=start))


def shuffle_tables(tables: io.Tables, seed: int = 1) -> io.Tables:
    """Same records, another physical row order in every table."""
    names = ("groups", "companies", "banking_products", "debt_products", "debt_schedule_config",
             "transactions", "invoices", "balances")
    return replace(
        tables,
        **{name: getattr(tables, name).sample(fraction=1.0, shuffle=True, seed=seed + index)
           for index, name in enumerate(names)},
    )


# --------------------------------------------------------------------------
# comparisons and small statistics
# --------------------------------------------------------------------------


def _flatten(frame: pl.DataFrame) -> pl.DataFrame:
    while True:
        structs = [name for name, dtype in frame.schema.items() if isinstance(dtype, pl.Struct)]
        if not structs:
            break
        for name in structs:
            fields = [pl.col(name).struct.field(item.name).alias(f"{name}.{item.name}")
                      for item in frame.schema[name].fields]
            frame = frame.with_columns(fields).drop(name)
    for name, dtype in frame.schema.items():
        if isinstance(dtype, pl.List):
            if isinstance(dtype.inner, (pl.Struct, pl.List)):
                frame = frame.with_columns(pl.col(name).list.len().alias(name))
            else:
                frame = frame.with_columns(pl.col(name).cast(pl.List(pl.String)).list.join("|"))
    return frame


def compare_scores(
    left: pl.DataFrame, right: pl.DataFrame, tol: float = 1e-9, *, keys: Sequence[str] = _KEYS,
    ignore: Sequence[str] = ("dataset_hash",), rel: float = 0.0,
) -> dict[str, Any]:
    """Joins two frames on ``keys``: float columns (struct fields included)
    within ``tol`` with nulls in the same places, every other column equal.

    Returns ``{n, missing_left, missing_right, max_abs_diff, rows_beyond_tol,
    categorical_mismatches, columns_differing, tol, pass}``.
    """
    keys = list(keys)
    left = _flatten(left.drop([name for name in ignore if name in left.columns]))
    right = _flatten(right.drop([name for name in ignore if name in right.columns]))
    shared = [name for name in left.columns if name in right.columns and name not in keys]
    both = left.join(right, on=keys, how="inner", suffix="__r")
    result: dict[str, Any] = {
        "n": both.height,
        "missing_left": right.join(left, on=keys, how="anti").height,
        "missing_right": left.join(right, on=keys, how="anti").height,
        "columns_only_one_side": sorted(set(left.columns) ^ set(right.columns)),
    }
    exprs = []
    for name in shared:
        one, other = pl.col(name), pl.col(f"{name}__r")
        if left.schema[name].is_float() or right.schema[name].is_float():
            gap = (one.cast(pl.Float64) - other.cast(pl.Float64)).abs()
            exprs.append(gap.max().alias(f"{name}|max"))
            allowed = tol + rel * other.cast(pl.Float64).abs().fill_null(0.0)  # rel: for amounts in EUR
            exprs.append(((gap > allowed).fill_null(False) | (one.is_null() != other.is_null())).sum().alias(f"{name}|bad"))
        else:
            exprs.append(one.ne_missing(other).sum().alias(f"{name}|bad"))
    stats = both.select(exprs).row(0, named=True) if exprs and both.height else {}
    worst, beyond, categorical, differing = 0.0, 0, 0, {}
    for name in shared:
        bad = int(stats.get(f"{name}|bad") or 0)
        if f"{name}|max" in stats:
            worst = max(worst, float(stats[f"{name}|max"] or 0.0))
            beyond += bad
        else:
            categorical += bad
        if bad:
            differing[name] = bad
    top = sorted(differing, key=lambda name: (-differing[name], name))[:8]
    result.update(
        max_abs_diff=worst, rows_beyond_tol=beyond, categorical_mismatches=categorical,
        columns_differing={name: differing[name] for name in top}, tol=tol,
    )
    result["pass"] = bool(
        both.height and not result["missing_left"] and not result["missing_right"] and not differing
    )
    return result


def _alert_keys(alerts: Sequence[Alert], until: date | None = None, groups: set[str] | None = None) -> list[tuple]:
    return sorted(
        (alert.id, alert.state)
        for alert in alerts
        if (until is None or alert.month <= until) and (groups is None or alert.group_id in groups)
    )


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    for value in np.unique(values):  # average rank on ties
        tied = values == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    one, other = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if len(one) < 3 or len(one) != len(other):
        return None
    a, b = _ranks(one), _ranks(other)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def eta_squared(values: Sequence[float], labels: Sequence[Any]) -> float:
    """Share of the variance of ``values`` between the cells of ``labels``."""
    data = np.asarray(values, dtype=float)
    _, codes = np.unique(np.asarray([str(item) for item in labels]), return_inverse=True)
    return _eta(data, codes)


def _eta(data: np.ndarray, codes: np.ndarray) -> float:
    total = float(((data - data.mean()) ** 2).sum()) if len(data) else 0.0
    if total <= 0:
        return 0.0
    counts = np.bincount(codes)
    sums = np.bincount(codes, weights=data)
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    return float((counts * (means - data.mean()) ** 2).sum() / total)


def excess_eta_squared(
    values: Sequence[float], labels: Sequence[Any], *, draws: int = 200, seed: int = 7
) -> dict[str, Any]:
    """eta-squared minus its mean over random partitions with the same cell sizes."""
    data = np.asarray(values, dtype=float)
    if len(data) < 3:
        return {"n": len(data), "cells": 0, "eta2": None, "null_eta2": None, "excess": None}
    _, codes = np.unique(np.asarray([str(item) for item in labels]), return_inverse=True)
    rng = np.random.default_rng(seed)
    observed = _eta(data, codes)
    null = float(np.mean([_eta(data, rng.permutation(codes)) for _ in range(draws)]))
    return {"n": len(data), "cells": int(codes.max()) + 1, "eta2": observed, "null_eta2": null,
            "excess": observed - null}


def _quantile(values: Sequence[float], q: float) -> float | None:
    return float(np.quantile(np.asarray(values, dtype=float), q)) if len(values) else None


def _metric(label: str, value: Any, unit: str = "") -> dict[str, Any]:
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float):
        value = float(f"{value:.6g}") if math.isfinite(value) else None
    elif isinstance(value, str):
        value = value[:80]
    elif value is not None and not isinstance(value, (bool, int)):
        value = str(value)[:80]
    return {"label": label[:400] or "-", "value": value, "unit": unit[:24]}


def _pct(value: float | None) -> str:
    return "n/d" if value is None else f"{100 * value:.1f}%".replace(".", ",")


def _num(value: float | None, decimals: int = 1) -> str:
    return "n/d" if value is None else f"{value:.{decimals}f}".replace(".", ",")


# --------------------------------------------------------------------------
# checks that re-run the engine on tables in memory
# --------------------------------------------------------------------------


def pick_groups(scored: Scored, n_groups: int, seed: int = 7) -> list[str]:
    """``n_groups`` groups drawn with ``seed``, round-robin over the strata
    (size band, has invoices) of the last month."""
    strata: dict[tuple, list[str]] = defaultdict(list)
    for group_id, items in _groups(scored).items():
        last = items[-1]
        strata[(str(last.row.size_band), bool(last.row.has_invoices))].append(group_id)
    rng = random.Random(seed)
    queues = []
    for key in sorted(strata):
        ids = sorted(strata[key])
        rng.shuffle(ids)
        queues.append(ids)
    chosen: list[str] = []
    while queues and len(chosen) < n_groups:
        for queue in queues:
            if queue and len(chosen) < n_groups:
                chosen.append(queue.pop())
        queues = [queue for queue in queues if queue]
    return sorted(chosen)


def check_isolation(scored: Scored, *, n_groups: int = 60, seed: int = 7, tol: float = 1e-9) -> dict[str, Any]:
    """Scores ``n_groups`` groups alone and compares with the full run."""
    chosen = pick_groups(scored, n_groups, seed)
    alone = score_core(subset_tables(scored.tables, chosen), scored.params)
    result = compare_scores(alone.frame, scored.frame.filter(pl.col("group_id").is_in(chosen)), tol)
    result["alerts_equal"] = _alert_keys(alone.alerts) == _alert_keys(scored.alerts, groups=set(chosen))
    result["n_groups"] = len(chosen)
    result["pass"] = bool(result["pass"] and result["alerts_equal"])
    result["summary"] = (
        f"{len(chosen)} grupos puntuados en solitario ({result['n']} entidad-mes): diferencia máxima "
        f"{result['max_abs_diff']:.1e} frente a la cartera completa (tolerancia {tol:.0e})."
    )
    if not result["pass"]:
        result["summary"] += f" Columnas que difieren: {', '.join(result['columns_differing']) or 'alertas o filas'}."
    result["metrics"] = [
        _metric("Grupos puntuados en solitario", len(chosen), "grupos"),
        _metric("Entidad-mes comparados", result["n"], "filas"),
        _metric("Diferencia máxima", result["max_abs_diff"], "puntos"),
        _metric("Alertas idénticas", result["alerts_equal"]),
    ]
    return result


def check_truncation(
    scored: Scored, *, months: Sequence[date] | None = None, tol: float = 1e-9
) -> dict[str, Any]:
    """For every cut month t: tables cut at the end of t, scored, and the rows
    with month <= t must equal those of the full run (alerts included). Panel
    facts are compared too, to name the column behind a difference. Groups
    holding an account whose rolled balance reaches the sentinel magnitude are
    also left out once, to tell that cause apart from a real look-ahead."""
    window = scored.tables.window
    if months is None:
        months = [_shift_month(window.last_month, -offset) for offset in TRUNCATION_OFFSETS]
    months = [month for month in months if window.first_month <= month < window.last_month]
    owners = dict(scored.clean.products.select("product_id", "group_id").iter_rows())
    cuts: dict[str, Any] = {}
    for month in months:
        cut = score_core(truncate_tables(scored.tables, month, scored.params), scored.params)
        full = scored.frame.filter(pl.col("month") <= month)
        scores = compare_scores(cut.frame, full, tol)
        facts = compare_scores(cut.panel, scored.panel.filter(pl.col("month") <= month), 1e-6, rel=1e-9)
        scores["panel_columns_differing"] = facts["columns_differing"]
        scores["alerts_equal"] = _alert_keys(cut.alerts) == _alert_keys(scored.alerts, until=month)
        scores["pass"] = bool(scores["pass"] and scores["alerts_equal"])
        crossers = roll_balances(scored.tables, _month_end(month), scored.params)[1]
        groups = sorted({owners[product] for product in crossers if owners.get(product)})
        scores["accounts_rolled_over_sentinel"] = len(crossers)
        scores["groups_rolled_over_sentinel"] = len(groups)
        if groups and not scores["pass"]:
            outside = ~pl.col("group_id").is_in(groups)
            rest = compare_scores(cut.frame.filter(outside), full.filter(outside), tol)
            scores["max_abs_diff_other_groups"] = rest["max_abs_diff"]
            scores["pass_other_groups"] = rest["pass"]
        cuts[f"{month:%Y-%m}"] = scores
    worst = max((item["max_abs_diff"] for item in cuts.values()), default=0.0)
    rows = sum(item["n"] for item in cuts.values())
    bad = sum(item["rows_beyond_tol"] + item["categorical_mismatches"] for item in cuts.values())
    crossing = sum(item["accounts_rolled_over_sentinel"] for item in cuts.values())
    passed = bool(cuts) and all(item["pass"] for item in cuts.values())
    summary = (
        f"Cortes en {', '.join(cuts) or 'ningún mes'}: {rows} entidad-mes anteriores al corte, diferencia máxima "
        f"{worst:.1e}. Excepciones declaradas: {'; '.join(SNAPSHOT_EXCEPTIONS)}."
    )
    if cuts and not passed:
        failing = [item for item in cuts.values() if not item["pass"]]
        summary = f"Cortes en {', '.join(cuts)}: {bad} valores cambian al cortar (máx. {_num(worst, 2)} puntos). "
        if all(item.get("pass_other_groups") for item in failing):
            accounts = sum(item["accounts_rolled_over_sentinel"] for item in failing)
            summary += (
                f"Causa: en {accounts} cuenta(s) el saldo retrocedido hasta el corte alcanza la magnitud de centinela "
                "y el motor lo descarta como marcador; fuera de esos grupos el resultado es idéntico."
            )
        else:
            columns = Counter()
            for item in failing:
                columns.update(item["panel_columns_differing"] or item["columns_differing"])
            summary += (
                "Causa probable: columnas que leen el futuro o la foto actual: "
                f"{', '.join(list(dict(columns.most_common(5))))}."
            )
    return {
        "pass": passed if cuts else None, "cuts": cuts, "max_abs_diff": worst, "n": rows,
        "values_differing": bad, "accounts_rolled_over_sentinel": crossing,
        "snapshot_exceptions": list(SNAPSHOT_EXCEPTIONS), "tol": tol, "summary": summary,
        "metrics": [
            _metric("Meses de corte", ", ".join(cuts)),
            _metric("Entidad-mes comparados", rows, "filas"),
            _metric("Diferencia máxima", worst, "puntos"),
            _metric("Valores que cambian", bad, "valores"),
            _metric("Cuentas con saldo retrocedido sobre el centinela", crossing, "cuentas"),
        ],
    }


def check_determinism(scored: Scored, *, group_ids: Sequence[str] | None = None, seed: int = 1) -> dict[str, Any]:
    """A second run and a run on row-shuffled tables must give equal frames.
    ``group_ids`` restricts both runs to a subset (quick mode)."""
    tables, reference, alerts = scored.tables, scored.frame, _alert_keys(scored.alerts)
    if group_ids is not None:
        tables = subset_tables(tables, group_ids)
        first = score_core(tables, scored.params)
        reference, alerts = first.frame, _alert_keys(first.alerts)
    again = score_core(tables, scored.params)
    shuffled = score_core(shuffle_tables(tables, seed), scored.params)
    second = bool(again.frame.equals(reference) and _alert_keys(again.alerts) == alerts)
    shuffle = compare_scores(shuffled.frame, reference, 0.0)
    shuffle_ok = bool(shuffle["pass"] and _alert_keys(shuffled.alerts) == alerts)
    summary = (
        f"Segunda ejecución {'idéntica' if second else 'distinta'}; con las filas barajadas "
        f"{'idéntica' if shuffle_ok else 'distinta'} ({reference.height} entidad-mes)."
    )
    if not shuffle_ok:
        summary += f" Columnas que dependen del orden de las filas: {', '.join(shuffle['columns_differing']) or 'alertas'}."
    return {
        "pass": second and shuffle_ok, "second_run_equal": second, "shuffled_equal": shuffle_ok,
        "shuffled_max_abs_diff": shuffle["max_abs_diff"], "shuffled_columns_differing": shuffle["columns_differing"],
        "n": reference.height, "summary": summary,
        "metrics": [
            _metric("Segunda ejecución idéntica", second),
            _metric("Filas barajadas: resultado idéntico", shuffle_ok),
            _metric("Diferencia máxima con filas barajadas", shuffle["max_abs_diff"], "puntos"),
            _metric("Entidad-mes comparados", reference.height, "filas"),
        ],
    }


def history_truncation(
    scored: Scored, *, lengths: Sequence[int] = (6, 9, 12), max_groups: int | None = None
) -> dict[str, Any]:
    """Groups observed over the whole window re-scored with only their last k
    months visible: absolute difference of the last score against the full
    history. Justifies the eligibility cut and the history confidence table."""
    window = scored.tables.window
    full = {
        group_id: items[-1]
        for group_id, items in _groups(scored).items()
        if items[0].row.month == window.first_month and items[-1].row.month == window.last_month
        and items[-1].parts.feed_live
    }
    ids = sorted(full)[: max_groups or None]
    by_length: dict[str, Any] = {}
    for length in lengths:
        start = _shift_month(window.last_month, -(length - 1))
        if not ids or start <= window.first_month:
            continue
        cut = score_core(tail_tables(scored.tables, ids, start), scored.params)
        last = {key[1]: items[-1] for key, items in _entities(cut.months).items() if key[0] == "group"}
        gaps, bands, abstained = [], 0, 0
        for group_id in ids:
            if group_id not in last or last[group_id].row.month != window.last_month:
                continue
            gaps.append(abs(last[group_id].parts.score - full[group_id].parts.score))
            bands += last[group_id].parts.band != full[group_id].parts.band
            abstained += bool(last[group_id].parts.abstained)
        if gaps:
            by_length[str(length)] = {
                "n": len(gaps), "median_abs_diff": float(median(gaps)), "p90_abs_diff": _quantile(gaps, 0.9),
                "band_change_share": bands / len(gaps), "abstained_share": abstained / len(gaps),
            }
    text = "; ".join(
        f"{length} meses: {_num(item['median_abs_diff'])} puntos" for length, item in by_length.items()
    )
    return {
        "pass": None, "n_groups": len(ids), "by_length": by_length,
        "summary": (
            f"{len(ids)} grupos con la ventana completa, puntuados viendo solo sus últimos meses. "
            f"Diferencia absoluta mediana del score: {text or 'sin grupos elegibles'}."
        ),
        "metrics": [_metric("Grupos con historia completa", len(ids), "grupos")] + [
            metric
            for length, item in by_length.items()
            for metric in (
                _metric(f"Diferencia mediana con {length} meses", item["median_abs_diff"], "puntos"),
                _metric(f"Cambian de banda con {length} meses", item["band_change_share"], "proporción"),
            )
        ],
    }


# --------------------------------------------------------------------------
# checks on the scored result
# --------------------------------------------------------------------------


def check_additivity(scored: Scored, tol: float = 1e-9) -> dict[str, Any]:
    """Score and delta identities on every entity-month, carried months included."""
    worst_score = worst_level = worst_delta = worst_weights = 0.0
    n = deltas = 0
    for items in _entities(scored.months).values():
        previous = None
        for item in items:
            parts = item.parts
            n += 1
            explained = parts.base + sum(parts.contributions.values()) - parts.penalty - parts.cap_adjustment
            worst_score = max(worst_score, abs(parts.score - explained))
            worst_level = max(worst_level, abs(parts.score - (parts.level_weighted - parts.penalty - parts.cap_adjustment)))
            if parts.weights_effective:
                worst_weights = max(worst_weights, abs(sum(parts.weights_effective.values()) - 1.0))
            if previous is not None:
                change = delta_parts(parts, previous)
                total = change.base + sum(change.contributions.values()) - change.penalty - change.cap_adjustment
                worst_delta = max(worst_delta, abs(change.score - total), abs(change.score - (parts.score - previous.score)))
                deltas += 1
            previous = parts
    worst = max(worst_score, worst_level, worst_delta, worst_weights)
    return {
        "pass": bool(n) and worst <= tol, "n": n, "n_deltas": deltas, "max_abs_residual": worst,
        "score_identity": worst_score, "level_identity": worst_level, "delta_identity": worst_delta,
        "weights_sum": worst_weights, "tol": tol,
        "summary": (
            f"Base más contribuciones menos penalización y tope reproduce el score en {n} entidad-mes y "
            f"{deltas} variaciones mensuales: residuo máximo {worst:.1e} (tolerancia {tol:.0e})."
        ),
        "metrics": [
            _metric("Entidad-mes comprobados", n, "filas"),
            _metric("Residuo máximo del score", worst_score, "puntos"),
            _metric("Residuo máximo de la variación mensual", worst_delta, "puntos"),
            _metric("Desvío máximo de la suma de pesos", worst_weights),
        ],
    }


def check_scale_invariance(
    scored: Scored, factor: float = 1024.0, *, group_ids: Sequence[str] | None = None, tol: float = 1e-6
) -> dict[str, Any]:
    """Pure core only: every EUR column of the panel times ``factor``, size
    band labels kept (the mirror gate and the size band are set in EUR)."""
    panel = scored.panel if group_ids is None else scored.panel.filter(pl.col("group_id").is_in(list(group_ids)))
    money = [name for name in PANEL_MONEY_COLUMNS if name in panel.columns]
    scaled = score_panel(panel.with_columns([pl.col(name) * factor for name in money]), scored.params)
    base = {(item.row.entity_kind, item.row.entity_id, item.row.month): item.parts for item in scored.months}
    worst, bands = 0.0, 0
    for item in scaled:
        reference = base[(item.row.entity_kind, item.row.entity_id, item.row.month)]
        worst = max(worst, abs(item.parts.score - reference.score))
        bands += item.parts.band != reference.band
    return {
        "pass": bool(scaled) and worst <= tol and bands == 0, "n": len(scaled), "factor": factor,
        "max_abs_diff": worst, "band_changes": bands, "tol": tol,
        "summary": (
            f"Importes multiplicados por {factor:g} en {len(scaled)} entidad-mes: diferencia máxima {worst:.1e} "
            "puntos. Se prueba el núcleo puro: el umbral de traspasos y la banda de tamaño están fijados en euros."
        ),
        "metrics": [
            _metric("Factor de escala", factor),
            _metric("Entidad-mes comprobados", len(scaled), "filas"),
            _metric("Diferencia máxima", worst, "puntos"),
            _metric("Cambios de banda", bands, "filas"),
        ],
    }


def _last_live(scored: Scored) -> list[EntityMonth]:
    """Group rows of the last month that are live, own-scored and not abstained."""
    return [
        items[-1]
        for items in _groups(scored).values()
        if items[-1].row.month == scored.last_month and items[-1].parts.feed_live
        and items[-1].parts.carried_from is None and not items[-1].parts.abstained
    ]


def _without(item: EntityMonth, keys: Sequence[str]) -> dict[str, PillarResult]:
    return {
        key: PillarResult(key=key, score=None, gates=("ablated",)) if key in keys else result
        for key, result in item.pillars.items()
    }


def _ablate(items: Sequence[EntityMonth], keys: Sequence[str], params: Params) -> dict[str, Any]:
    chosen = [item for item in items if any(item.parts.pillar_scores.get(key) is not None for key in keys)]
    full = [item.parts.score for item in chosen]
    cut = [aggregate(_without(item, keys), item.row, params).score for item in chosen]
    shifts = [after - before for before, after in zip(full, cut)]
    bands = sum(band_of(after, params.bands) != item.parts.band for item, after in zip(chosen, cut))
    return {
        "n": len(chosen),
        "mean_shift": float(np.mean(shifts)) if shifts else None,
        "mean_abs_shift": float(np.mean(np.abs(shifts))) if shifts else None,
        "p90_abs_shift": _quantile([abs(value) for value in shifts], 0.9),
        "spearman": spearman(full, cut),
        "band_change_share": bands / len(chosen) if chosen else None,
    }


def paired_ablation(scored: Scored, *, max_mean_shift: float = 5.0, min_spearman: float = 0.8) -> dict[str, Any]:
    """Same groups, last month, with and without the invoice pillars (payments
    and collections set to None, then re-aggregated); also without debt."""
    items = _last_live(scored)
    invoices = _ablate(items, ("payments", "collections"), scored.params)
    debt = _ablate(items, ("debt",), scored.params)
    ok = None
    if invoices["n"] >= 3 and invoices["spearman"] is not None:
        ok = abs(invoices["mean_shift"]) <= max_mean_shift and invoices["spearman"] >= min_spearman
    summary = (
        f"{invoices['n']} grupos con facturas puntuados también sin los pilares de pagos y cobros: desplazamiento "
        f"medio {_num(invoices['mean_shift'])} puntos, Spearman {_num(invoices['spearman'], 2)}, "
        f"{_pct(invoices['band_change_share'])} cambia de banda."
    )
    if ok is False:
        summary += " Aviso: el score con y sin facturas no es intercambiable; comparar grupos dentro de la misma rama."
    return {
        "pass": True if ok else None, "warning": ok is False, "invoices": invoices, "debt": debt,
        "thresholds": {"max_mean_shift": max_mean_shift, "min_spearman": min_spearman},
        "summary": summary,
        "metrics": [
            _metric("Grupos con pilares de facturas", invoices["n"], "grupos"),
            _metric("Desplazamiento medio sin facturas", invoices["mean_shift"], "puntos"),
            _metric("Desplazamiento absoluto medio sin facturas", invoices["mean_abs_shift"], "puntos"),
            _metric("Spearman con y sin facturas", invoices["spearman"]),
            _metric("Cambian de banda sin facturas", invoices["band_change_share"], "proporción"),
            _metric("Grupos con pilar de deuda", debt["n"], "grupos"),
            _metric("Desplazamiento medio sin deuda", debt["mean_shift"], "puntos"),
            _metric("Spearman con y sin deuda", debt["spearman"]),
        ],
    }


def group_attributes(scored: Scored, *, min_cell: int = 5) -> dict[str, dict[str, str]]:
    """ERP tier and main bank (most booked rows) per group; banks with fewer
    than ``min_cell`` groups are pooled."""
    try:
        from .profile import erp_tier
    except Exception:  # noqa: BLE001 - the raw label still partitions the groups
        def erp_tier(erp: str | None) -> tuple[str | None, str]:
            return erp, (erp or "NONE").strip() or "NONE"

    found: dict[str, dict[str, str]] = defaultdict(dict)
    groups = scored.tables.groups
    declared = dict(groups.select("group_id", "erp").iter_rows()) if "erp" in groups.columns else {}
    modal: dict[str, Counter] = defaultdict(Counter)
    if "erp" in scored.tables.companies.columns:
        for group_id, erp in scored.tables.companies.select("group_id", "erp").iter_rows():
            if (erp or "").strip():
                modal[group_id][erp] += 1
    for group_id in scored.tables.companies["group_id"].unique().to_list():
        erp = declared.get(group_id) or (modal[group_id].most_common(1)[0][0] if modal[group_id] else None)
        found[group_id]["erp_tier"] = erp_tier(erp)[1]
    products = scored.clean.products
    if "bank_name" in products.columns:
        rows = (
            scored.clean.transactions.group_by("product_id").len()
            .join(products.select("product_id", "group_id", "bank_name"), on="product_id")
            .filter(pl.col("bank_name").is_not_null())
            .group_by("group_id", "bank_name").agg(pl.col("len").sum())
            .sort("group_id", "len", "bank_name", descending=[False, True, False])
            .group_by("group_id", maintain_order=True).first()
        )
        banks = dict(rows.select("group_id", "bank_name").iter_rows())
        sizes = Counter(banks.values())
        for group_id, bank in banks.items():
            found[group_id]["main_bank"] = bank if sizes[bank] >= min_cell else "otros"
    return found


def neutrality(scored: Scored, *, draws: int = 200, seed: int = 7, min_groups: int = 30) -> dict[str, Any]:
    """Excess eta-squared of the group score over random partitions with the
    same cell sizes, for every one of ``NEUTRALITY_DIMENSIONS``."""
    items = _last_live(scored)
    attributes = group_attributes(scored)
    scores = [item.parts.score for item in items]
    labels = {
        "size_band": [str(item.parts.size_band) for item in items],
        "erp_tier": [attributes.get(item.row.entity_id, {}).get("erp_tier") for item in items],
        "main_bank": [attributes.get(item.row.entity_id, {}).get("main_bank") for item in items],
        "coverage_branch": [item.parts.branch for item in items],
    }
    dimensions: dict[str, Any] = {}
    for name, values in labels.items():
        known = [(score, label) for score, label in zip(scores, values) if label is not None]
        dimensions[name] = excess_eta_squared(
            [score for score, _ in known], [label for _, label in known], draws=draws, seed=seed
        )
    monthly = [
        item for group in _groups(scored).values() for item in group
        if item.parts.feed_live and item.parts.carried_from is None and not item.parts.abstained
    ]
    dimensions["calendar_month"] = excess_eta_squared(
        [item.parts.score for item in monthly], [item.row.month.month for item in monthly], draws=draws, seed=seed
    )
    measured = {name: item["excess"] for name, item in dimensions.items() if item["excess"] is not None}
    worst = max(measured.values(), default=None)
    small = len(items) < min_groups  # a partition of a handful of groups says nothing
    failing = sorted(name for name, value in measured.items() if value > NEUTRALITY_FAIL and not small)
    warned = sorted(name for name, value in measured.items() if NEUTRALITY_OK < value <= NEUTRALITY_FAIL and not small)
    names = {"size_band": "tamaño", "erp_tier": "ERP", "main_bank": "banco principal",
             "calendar_month": "mes del año", "coverage_branch": "rama de cobertura"}
    text = ", ".join(f"{names[name]} {_num(value, 3)}" for name, value in measured.items())
    summary = f"Exceso de eta² sobre una partición aleatoria del mismo tamaño ({len(items)} grupos): {text or 'sin datos'}."
    if failing:
        summary += f" Falla (> {NEUTRALITY_FAIL:.2f}): {', '.join(names[name] for name in failing)}."
    if warned:
        summary += f" Aviso (> {NEUTRALITY_OK:.2f}): {', '.join(names[name] for name in warned)}: leer el score dentro de cada celda."
    passed = None if worst is None or warned or small else True
    if small:
        summary += f" Menos de {min_groups} grupos: sin veredicto."
    return {
        "pass": False if failing else passed, "warning": bool(warned), "n_groups": len(items),
        "dimensions": dimensions, "worst_excess": worst,
        "thresholds": {"ok": NEUTRALITY_OK, "fail": NEUTRALITY_FAIL}, "summary": summary,
        "metrics": [_metric("Grupos del último mes", len(items), "grupos")] + [
            _metric(f"Exceso de eta² por {names[name]}", item["excess"]) for name, item in dimensions.items()
        ] + [_metric(f"eta² observado por {names[name]}", item["eta2"]) for name, item in dimensions.items()],
    }


def penalty_by_branch(scored: Scored, *, top: int = 6) -> dict[str, Any]:
    """Mean penalty and share of months with a penalty, by coverage branch
    (live, own-scored group-months)."""
    cells: dict[str, list[float]] = defaultdict(list)
    for items in _groups(scored).values():
        for item in items:
            if item.parts.feed_live and item.parts.carried_from is None:
                cells[item.parts.branch].append(item.parts.penalty)
    branches = {
        branch: {"n": len(values), "mean_penalty": float(np.mean(values)),
                 "penalised_share": sum(value > 0 for value in values) / len(values)}
        for branch, values in sorted(cells.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    }
    every = [value for values in cells.values() for value in values]
    overall = float(np.mean(every)) if every else None
    shown = list(branches.items())[:top]
    spread = max((item["mean_penalty"] for _, item in shown), default=0.0) - min(
        (item["mean_penalty"] for _, item in shown), default=0.0
    )
    return {
        "pass": None, "n": len(every), "mean_penalty": overall, "branches": branches, "spread_top_branches": spread,
        "summary": (
            f"Penalización media {_num(overall, 2)} puntos en {len(every)} grupo-mes con feed activo; entre las "
            f"{len(shown)} ramas más frecuentes varía {_num(spread, 2)} puntos."
        ),
        "metrics": [_metric("Penalización media", overall, "puntos")] + [
            metric
            for branch, item in shown
            for metric in (
                _metric(f"Penalización media · {branch}", item["mean_penalty"], "puntos"),
                _metric(f"Meses con penalización · {branch}", item["penalised_share"], "proporción"),
            )
        ],
    }


def perturbed_params(params: Params, rng: random.Random, lam: float, spread: float = 0.10) -> Params:
    """Weights moved by up to ``spread`` each, floored and renormalised; another lambda."""
    weights = {key: max(0.01, params.weights[key] + rng.uniform(-spread, spread)) for key in PILLAR_KEYS}
    total = sum(weights.values())
    return replace(
        params, weights={key: value / total for key, value in weights.items()},
        penalty=replace(params.penalty, lam=lam),
    )


def rank_stability(
    scored: Scored, *, draws: int = 200, seed: int = 7, lambdas: Sequence[float] = (0.3, 0.5, 0.7),
    min_spearman: float = 0.9,
) -> dict[str, Any]:
    """Re-aggregates the last month under ``draws`` seeded perturbations of the
    weights (+-10 points, renormalised) and of lambda: Spearman of the group
    ranks against the baseline and share of groups changing band."""
    items = _last_live(scored)
    base = [item.parts.score for item in items]
    rng = random.Random(seed)
    correlations, changes = [], []
    for draw in range(draws if len(items) >= 3 else 0):
        params = perturbed_params(scored.params, rng, lambdas[draw % len(lambdas)])
        scores = [aggregate(item.pillars, item.row, params).score for item in items]
        value = spearman(base, scores)
        if value is not None:
            correlations.append(value)
        changes.append(
            sum(band_of(score, params.bands) != item.parts.band for item, score in zip(items, scores)) / len(items)
        )
    low = _quantile(correlations, 0.05)
    ok = None if low is None else low >= min_spearman
    summary = (
        f"{len(correlations)} perturbaciones de ±10 puntos en los pesos y lambda en {{{', '.join(str(v) for v in lambdas)}}} "
        f"sobre {len(items)} grupos: Spearman mediano {_num(_quantile(correlations, 0.5), 3)} (p5 {_num(low, 3)}), "
        f"{_pct(float(np.mean(changes)) if changes else None)} de los grupos cambia de banda de media."
    )
    if ok is False:
        summary += " Aviso: el orden es sensible a los pesos."
    return {
        "pass": True if ok else None, "warning": ok is False, "n_groups": len(items), "draws": len(correlations),
        "spearman_median": _quantile(correlations, 0.5), "spearman_p05": low,
        "spearman_min": min(correlations, default=None),
        "band_change_share_mean": float(np.mean(changes)) if changes else None,
        "band_change_share_p95": _quantile(changes, 0.95), "lambdas": list(lambdas), "summary": summary,
        "metrics": [
            _metric("Grupos ordenados", len(items), "grupos"),
            _metric("Perturbaciones", len(correlations)),
            _metric("Spearman mediano", _quantile(correlations, 0.5)),
            _metric("Spearman p5", low),
            _metric("Grupos que cambian de banda (media)", float(np.mean(changes)) if changes else None, "proporción"),
            _metric("Grupos que cambian de banda (p95)", _quantile(changes, 0.95), "proporción"),
        ],
    }


def conditional_rates(series: Sequence[Sequence[bool | None]], lag: int = 6) -> dict[str, Any]:
    """P(flag at t+lag | flag at t), P(flag at t+lag | no flag at t) and the
    base rate over every pair (t, t+lag) with both ends known."""
    table = Counter()
    for flags in series:
        for now, later in zip(flags, flags[lag:]):
            if now is not None and later is not None:
                table[(bool(now), bool(later))] += 1
    flagged, clear = table[(True, True)] + table[(True, False)], table[(False, True)] + table[(False, False)]
    pairs = flagged + clear
    return {
        "pairs": pairs, "flagged": flagged,
        "p_given_flag": table[(True, True)] / flagged if flagged else None,
        "p_given_clear": table[(False, True)] / clear if clear else None,
        "base_rate": (table[(True, True)] + table[(False, True)]) / pairs if pairs else None,
    }


def persistence(scored: Scored, *, lag: int = 6, low_score: float = 40.0, min_lift: float = 2.0) -> dict[str, Any]:
    """Group level: a score under ``low_score`` and a negative cash balance,
    ``lag`` months later, against their base rates. Stale months are unknown."""
    low, cash, liquidity, cash_any = [], [], [], []
    for items in _groups(scored).values():
        by_month = {item.row.month: item for item in items}
        span = months_between(items[0].row.month, items[-1].row.month) + 1
        months = [_shift_month(items[0].row.month, index) for index in range(span)]
        live = [by_month.get(month) for month in months]
        cash_any.append([
            None if item is None or item.row.cash_month_end is None else item.row.cash_month_end < 0 for item in live
        ])
        live = [item if item is not None and item.parts.feed_live and item.parts.carried_from is None else None for item in live]
        low.append([None if item is None else item.parts.score < low_score for item in live])
        cash.append([None if item is None or item.row.cash_month_end is None else item.row.cash_month_end < 0 for item in live])
        liquidity.append([
            None if item is None or item.row.cash_month_end is None
            else item.row.cash_month_end + (item.row.headroom or 0.0) < 0 for item in live
        ])
    score_rates, cash_rates, liquidity_rates, cash_any_rates = (
        conditional_rates(series, lag) for series in (low, cash, liquidity, cash_any)
    )
    ok = None
    if score_rates["flagged"] >= 20 and score_rates["base_rate"]:
        ok = score_rates["p_given_flag"] >= min_lift * score_rates["base_rate"]
    summary = (
        f"Un grupo con score bajo {low_score:g} sigue por debajo {lag} meses después el {_pct(score_rates['p_given_flag'])} "
        f"de las veces (tasa base {_pct(score_rates['base_rate'])}, {score_rates['flagged']} casos). Caja negativa: "
        f"{_pct(cash_rates['p_given_flag'])} sigue negativa frente a {_pct(cash_rates['p_given_clear'])} cuando era positiva."
    )
    if ok is None:
        summary += " Casos insuficientes para un veredicto."
    return {
        "pass": ok, "lag_months": lag, "low_score": score_rates, "negative_cash": cash_rates,
        "negative_cash_plus_headroom": liquidity_rates, "negative_cash_stale_months_included": cash_any_rates,
        "summary": summary,
        "metrics": [
            _metric(f"P(score < {low_score:g} a +{lag} | score < {low_score:g})", score_rates["p_given_flag"], "proporción"),
            _metric(f"Tasa base de score < {low_score:g} a +{lag}", score_rates["base_rate"], "proporción"),
            _metric("Casos con score bajo", score_rates["flagged"], "grupo-mes"),
            _metric(f"P(caja negativa a +{lag} | caja negativa)", cash_rates["p_given_flag"], "proporción"),
            _metric(f"P(caja negativa a +{lag} | caja positiva)", cash_rates["p_given_clear"], "proporción"),
            _metric("Casos con caja negativa", cash_rates["flagged"], "grupo-mes"),
            _metric(f"P(caja + disponible < 0 a +{lag} | < 0)", liquidity_rates["p_given_flag"], "proporción"),
            _metric("P(caja negativa | caja negativa), meses sin feed incluidos", cash_any_rates["p_given_flag"], "proporción"),
        ],
    }


def _netted_shares(transactions: pl.DataFrame) -> dict[str, float | None]:
    outflow = transactions.filter((pl.col("amount_cents") < 0) & ~pl.col("fx_excluded").fill_null(True))
    value = pl.col("amount_cents").abs() / 100 * pl.col("fx_rate")
    netted = pl.col("mirror_id").is_not_null()
    row = outflow.select(
        pl.len().alias("rows"), netted.sum().alias("netted_rows"), value.sum().alias("value"),
        value.filter(netted).sum().alias("netted_value"),
    ).row(0, named=True)
    return {
        "pairs": int(row["netted_rows"] or 0),
        "row_share": row["netted_rows"] / row["rows"] if row["rows"] else None,
        "value_share": row["netted_value"] / row["value"] if row["value"] else None,
    }


def netting_placebo(scored: Scored, *, offsets: Sequence[int] = (9, 10, 11), max_ratio: float = 0.10) -> dict[str, Any]:
    """Mirror recipe re-run with every positive leg moved 9 to 11 days later
    (same month key): outflow netted by the placebo against the real one."""
    transactions = scored.clean.transactions
    real = _netted_shares(transactions)
    added = [name for name in cleaning.CLEAN_TRANSACTION_COLUMNS
             if name in transactions.columns and name not in ("group_id", "currency", "product_type",
                                                              "product_family", "fx_rate", "fx_excluded", "orphan_product")]
    days = pl.int_range(pl.len()) % len(offsets) + min(offsets)
    shifted = transactions.drop(added).sort("transaction_id").with_columns(
        pl.when(pl.col("amount_cents") > 0).then(pl.col("date") + pl.duration(days=days))
        .otherwise(pl.col("date")).alias("date")
    )
    placebo = _netted_shares(cleaning.net_mirror_pairs(shifted, scored.params))
    ratio = placebo["value_share"] / real["value_share"] if real["value_share"] else None
    return {
        "pass": None if ratio is None else ratio <= max_ratio, "real": real, "placebo": placebo,
        "placebo_over_real": ratio, "offset_days": list(offsets),
        "summary": (
            f"El emparejamiento de traspasos retira el {_pct(real['value_share'])} del valor de las salidas; con las "
            f"entradas desplazadas {min(offsets)}-{max(offsets)} días solo encuentra el {_pct(placebo['value_share'])}."
        ),
        "metrics": [
            _metric("Valor de salidas emparejado", real["value_share"], "proporción"),
            _metric("Valor emparejado con fechas desplazadas", placebo["value_share"], "proporción"),
            _metric("Filas de salida emparejadas", real["row_share"], "proporción"),
            _metric("Filas emparejadas con fechas desplazadas", placebo["row_share"], "proporción"),
            _metric("Placebo sobre real", ratio),
        ],
    }


# --------------------------------------------------------------------------
# injected deteriorations (PanelRow level, pure core)
# --------------------------------------------------------------------------


def _winsorised_sum(monthly: Sequence[float], multiple: float) -> float:
    positive = sorted(value for value in monthly if value > 0)
    if not positive:
        return 0.0
    cap = multiple * float(median(positive))
    return float(sum(min(max(value, 0.0), cap) for value in monthly))


def _moved(value: float | None, delta: float, floor: float | None = 0.0) -> float | None:
    if value is None:
        return None
    return value + delta if floor is None else max(floor, value + delta)


def inject(
    rows: Sequence[PanelRow], kind: str, start: date, params: Params, *,
    drop: float = 0.30, ramp_months: int = 6, spike_multiple: float = 1.0,
) -> list[PanelRow]:
    """``rows`` of one entity with a deterioration injected from ``start`` on.

    spike: the outflow of ``start`` grows by ``spike_multiple`` x the median
      monthly outflow of the six months before, paid in advance: the following
      months pay that much less, so cash dips for one month and comes back;
    step: operating inflow ``drop`` lower from ``start`` on, for good;
    ramp: the same level reached linearly over ``ramp_months``.
    Cash (month end and intra-month minimum) loses the cumulative shortfall.
    Trailing windows move by the change of their own recipe on the monthly
    series (medians, winsorised sums, like-for-like means in proportion), so
    months before ``start`` and untouched columns stay bit-identical.
    """
    if kind not in INJECTION_KINDS:
        raise ValueError(f"unknown injection {kind!r}")
    ordered = sorted(rows, key=lambda row: row.month)
    months = [row.month for row in ordered]
    if start not in months:
        raise ValueError(f"{start} is not a month of the entity")
    first, size = months.index(start), len(ordered)
    inflow = [row.op_inflow_1m or 0.0 for row in ordered]
    outflow = [row.op_outflow_1m or 0.0 for row in ordered]
    debt = [row.debt_service_1m or 0.0 for row in ordered]
    new_in, new_out = list(inflow), list(outflow)
    if kind == "spike":
        before = [outflow[index] + debt[index] for index in range(max(0, first - 6), first)]
        owed = spike_multiple * (float(median(before)) if before else outflow[first])
        new_out[first] += owed
        for index in range(first + 1, size):
            paid = min(owed, new_out[index])
            new_out[index] -= paid
            owed -= paid
            if owed <= 0:
                break
    else:
        for index in range(first, size):
            reached = 1.0 if kind == "step" else min(1.0, (index - first + 1) / ramp_months)
            new_in[index] = inflow[index] * (1.0 - drop * reached)
    drained, total = [0.0] * size, 0.0
    for index in range(first, size):
        total += (inflow[index] - new_in[index]) + (new_out[index] - outflow[index])
        drained[index] = total
    old_total = [outflow[index] + debt[index] for index in range(size)]
    new_total = [new_out[index] + debt[index] for index in range(size)]
    multiple = params.robust.monthly_winsor_multiple

    def negative(index: int, lost: float) -> bool:
        cash = ordered[index].cash_month_end
        return cash is not None and cash - lost + (ordered[index].headroom or 0.0) < 0

    def ratio(new: Sequence[float], old: Sequence[float]) -> float:
        return sum(new) / sum(old) if sum(old) > 0 else 1.0

    result = list(ordered[:first])
    for index in range(first, size):
        row = ordered[index]

        def span(values: Sequence[float], length: int, back: int = 0) -> list[float]:
            return list(values[max(0, index - back - length + 1): max(0, index - back + 1)])

        def capped(new: Sequence[float], old: Sequence[float], length: int) -> float:
            return _winsorised_sum(span(new, length), multiple) - _winsorised_sum(span(old, length), multiple)

        def mid(new: Sequence[float], old: Sequence[float], length: int) -> float:
            return float(median(span(new, length))) - float(median(span(old, length)))

        gone = sum(negative(at, drained[at]) for at in range(max(0, index - 5), index + 1)) - sum(
            negative(at, 0.0) for at in range(max(0, index - 5), index + 1)
        )
        changes = {
            "op_inflow_1m": new_in[index],
            "op_outflow_1m": new_out[index],
            "cash_month_end": _moved(row.cash_month_end, -drained[index], None),
            "cash_intra_month_min": _moved(row.cash_intra_month_min, -drained[index], None),
            "outflow_median_3m": _moved(row.outflow_median_3m, mid(new_total, old_total, 3)),
            "outflow_median_12m": _moved(row.outflow_median_12m, mid(new_total, old_total, 12)),
            "op_in_sum_6m_w": _moved(row.op_in_sum_6m_w, capped(new_in, inflow, 6)),
            "outflow_sum_6m_w": _moved(row.outflow_sum_6m_w, capped(new_total, old_total, 6)),
            "op_in_sum_12m_w": _moved(row.op_in_sum_12m_w, capped(new_in, inflow, 12)),
            "neg_liquidity_months_6m": min(6, max(0, (row.neg_liquidity_months_6m or 0) + gone)),
        }
        if row.op_in_lfl_recent_mean is not None:
            changes["op_in_lfl_recent_mean"] = row.op_in_lfl_recent_mean * ratio(span(new_in, 3), span(inflow, 3))
        if row.op_in_lfl_prior_mean is not None:
            changes["op_in_lfl_prior_mean"] = row.op_in_lfl_prior_mean * ratio(span(new_in, 6, 3), span(inflow, 6, 3))
        result.append(replace(row, **{name: value for name, value in changes.items() if hasattr(row, name)}))
    return result


def _deteriorating(item: EntityMonth, structural: bool = False) -> bool:
    verdict = item.trajectory
    if getattr(verdict, "direction", None) != "deteriorating":
        return False
    return not structural or getattr(verdict, "nature", None) == "structural"


_INJECTION_ALERTS = ("deterioration_structural", "level_critical", "cap_fired")


def injection_study(
    scored: Scored, *, starts_back: Sequence[int] = (11, 10, 9, 8), horizon: int = 9,
    min_score: float = 60.0, min_history: int = 8, kinds: Sequence[str] = INJECTION_KINDS,
) -> dict[str, Any]:
    """Spikes, steps and ramps injected into healthy groups observed over the
    whole window (score >= ``min_score`` and live feed the month before, live
    through the ``horizon``); only those groups are re-scored, through the pure
    core. A verdict or alert counts when the untouched run does not have it."""
    params, window = scored.params, scored.tables.window
    outcomes: dict[str, list[dict[str, Any]]] = {kind: [] for kind in kinds}
    healthy_windows = base_structural = 0
    fired = {alert.id for alert in scored.alerts if alert.state == "fired"}
    for group_id, base in _groups(scored).items():
        if base[0].row.month != window.first_month or base[-1].row.month != window.last_month:
            continue
        rows = [item.row for item in base]
        for back in starts_back:
            first = len(base) - 1 - back
            last = first + horizon - 1
            if first < min_history or last >= len(base):
                continue
            before = base[first - 1].parts
            if before.score < min_score or before.abstained or not all(
                item.parts.feed_live for item in base[first - 1: last + 1]
            ):
                continue
            healthy_windows += 1
            # no deterioration verdict of its own in the horizon: every call is the injection's
            quiet = not any(_deteriorating(item) for item in base[first: last + 1])
            base_structural += sum(
                alert.kind == "deterioration_structural" and alert.state == "fired" and alert.entity_id == group_id
                and alert.entity_kind == "group" and base[first].row.month <= alert.month <= base[last].row.month
                for alert in scored.alerts
            )
            for kind in kinds:
                injected = score_entity(inject(rows, kind, base[first].row.month, params), params)
                alerts = [
                    alert for alert in build_alerts(injected, params)
                    if alert.state == "fired" and alert.kind in _INJECTION_ALERTS and alert.id not in fired
                    and base[first].row.month <= alert.month <= base[last].row.month
                ]
                verdict = next(
                    (at - first for at in range(first, last + 1)
                     if _deteriorating(injected[at]) and not _deteriorating(base[at])), None,
                )
                called = next(
                    (at for at in range(first, last + 1)
                     if _deteriorating(injected[at], True) and not _deteriorating(base[at], True)), None,
                )
                structural = called is not None
                alert_at = min((alert.month for alert in alerts), default=None)
                outcomes[kind].append({
                    "size_band": str(before.size_band),
                    "quiet_base": quiet,
                    "verdict_delay": verdict,
                    "alert_delay": None if alert_at is None else months_between(base[first].row.month, alert_at),
                    "structural": structural,
                    "structural_delay": None if called is None else called - first,
                    "structural_horizon": None if called is None else str(getattr(injected[called].trajectory, "horizon", None)),
                    "drop_3m": base[min(first + 3, last)].parts.score - injected[min(first + 3, last)].parts.score,
                    "drop_end": base[last].parts.score - injected[last].parts.score,
                })
    live_months = sum(
        item.parts.feed_live and not item.parts.abstained for items in _groups(scored).values() for item in items
    )
    all_fired = sum(
        alert.kind == "deterioration_structural" and alert.state == "fired" and alert.entity_kind == "group"
        for alert in scored.alerts
    )
    untouched = {
        "group_years": live_months / 12, "alerts": all_fired,
        "rate_per_100_group_years": 100 * all_fired / (live_months / 12) if live_months else None,
        "healthy_group_years": healthy_windows * horizon / 12, "healthy_alerts": base_structural,
        "healthy_rate_per_100_group_years": (
            100 * base_structural / (healthy_windows * horizon / 12) if healthy_windows else None
        ),
    }
    by_kind = {kind: _injection_summary(items, horizon) for kind, items in outcomes.items()}
    spike = by_kind.get("spike", {}).get("p_structural")
    step = by_kind.get("step", {}).get("p_structural")
    ok = None
    if healthy_windows and spike is not None and step is not None:
        ok = spike <= P_STRUCTURAL_SPIKE_MAX and step >= P_STRUCTURAL_STEP_MIN
    summary = (
        f"{healthy_windows} inyecciones por tipo en grupos sanos. P(estructural | pico) {_pct(spike)} (objetivo ≤ 10%); "
        f"P(estructural | escalón -30% cobros) {_pct(step)} (objetivo ≥ 70%), veredicto a los "
        f"{_num(by_kind.get('step', {}).get('median_verdict_delay'))} meses (mediana). Sin inyección: "
        f"{_num(untouched['rate_per_100_group_years'])} alertas de deterioro por 100 grupo-años."
    )
    if not healthy_windows:
        summary = "Sin grupos sanos con la ventana completa y feed activo: estudio no aplicable."
    elif ok is False:
        causes = []
        if step is not None and step < P_STRUCTURAL_STEP_MIN:
            causes.append(
                f"el escalón solo resta {_num(by_kind['step']['mean_drop_end'])} puntos de media al final del horizonte "
                f"(umbral {params.trajectory.min_delta_points:g})"
            )
        if spike is not None and spike > P_STRUCTURAL_SPIKE_MAX:
            horizons = by_kind["spike"]["structural_by_horizon"]
            long_calls = sum(count for name, count in horizons.items() if name in ("long", "both"))
            total = sum(horizons.values())
            causes.append(
                f"en {long_calls} de {total} picos decide el horizonte largo (deriva), sin esperar a que el pico revierta"
                if long_calls * 2 >= total else
                f"en {total - long_calls} de {total} picos el horizonte corto sigue bajo el umbral dos meses seguidos"
            )
        summary += " Causa probable: " + "; ".join(causes) + "."
    bars = [
        {"label": f"mes +{delay}", "value": count}
        for delay, count in sorted(by_kind.get("step", {}).get("verdict_delay_distribution", {}).items())
        if delay != "none"
    ]
    if by_kind.get("step", {}).get("n"):
        bars.append({"label": "sin detectar", "value": by_kind["step"]["verdict_delay_distribution"].get("none", 0)})
    labels = {"spike": "pico", "step": "escalón", "ramp": "rampa"}
    metrics = [_metric("Inyecciones por tipo", healthy_windows), _metric("Horizonte de observación", horizon, "meses")]
    for kind, item in by_kind.items():
        metrics += [
            _metric(f"P(estructural | {labels[kind]})", item["p_structural"], "proporción"),
            _metric(f"Veredicto de deterioro · {labels[kind]}", item["p_verdict"], "proporción"),
            _metric(f"Retraso mediano del veredicto · {labels[kind]}", item["median_verdict_delay"], "meses"),
            _metric(f"Alerta disparada · {labels[kind]}", item["p_alert"], "proporción"),
            _metric(f"Retraso mediano de la alerta · {labels[kind]}", item["median_alert_delay"], "meses"),
            _metric(f"Caída media del score al final · {labels[kind]}", item["mean_drop_end"], "puntos"),
        ]
    quiet = by_kind.get("spike", {}).get("quiet_base") or {}
    untouched["healthy_windows"] = healthy_windows
    untouched["quiet_windows"] = quiet.get("n", 0)
    metrics += [
        _metric("Alertas de deterioro sin inyección", untouched["rate_per_100_group_years"], "por 100 grupo-años"),
        _metric("Ídem en los grupos sanos del estudio", untouched["healthy_rate_per_100_group_years"], "por 100 grupo-años"),
        _metric("Ventanas sanas sin veredicto de deterioro propio", quiet.get("n", 0), "ventanas"),
        _metric("P(estructural | pico) en esas ventanas", quiet.get("p_structural"), "proporción"),
    ]
    return {
        "pass": ok, "n_injections": healthy_windows, "horizon_months": horizon, "min_score": min_score,
        "by_kind": by_kind, "untouched": untouched,
        "targets": {"p_structural_spike_max": P_STRUCTURAL_SPIKE_MAX, "p_structural_step_min": P_STRUCTURAL_STEP_MIN},
        "summary": summary, "metrics": metrics, "bars": bars,
    }


def months_between(first: date, second: date) -> int:
    return (second.year - first.year) * 12 + second.month - first.month


def _injection_summary(items: Sequence[Mapping[str, Any]], horizon: int) -> dict[str, Any]:
    if not items:
        return {"n": 0, "p_structural": None, "p_verdict": None, "p_alert": None, "median_verdict_delay": None,
                "median_alert_delay": None, "mean_drop_3m": None, "mean_drop_end": None,
                "structural_by_horizon": {}, "median_structural_delay": None,
                "verdict_delay_distribution": {}, "alert_delay_distribution": {}, "by_size_band": {},
                "quiet_base": {"n": 0, "p_structural": None, "p_verdict": None, "structural_in_month_0": 0}}
    verdicts = [item["verdict_delay"] for item in items if item["verdict_delay"] is not None]
    alerts = [item["alert_delay"] for item in items if item["alert_delay"] is not None]

    def spread(delays: Sequence[int]) -> dict[str, int]:
        counts = Counter(delays)
        found = {str(delay): counts.get(delay, 0) for delay in range(horizon)}
        found["none"] = len(items) - len(delays)
        return found

    def delay(rows: Sequence[Mapping[str, Any]], name: str) -> float | None:
        found = [row[name] for row in rows if row[name] is not None]
        return float(median(found)) if found else None

    bands: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        bands[item["size_band"]].append(item)
    quiet = [item for item in items if item.get("quiet_base")]
    return {
        "n": len(items),
        "p_structural": sum(item["structural"] for item in items) / len(items),
        "p_verdict": len(verdicts) / len(items),
        "p_alert": len(alerts) / len(items),
        "median_verdict_delay": float(median(verdicts)) if verdicts else None,
        "median_alert_delay": float(median(alerts)) if alerts else None,
        "mean_drop_3m": float(np.mean([item["drop_3m"] for item in items])),
        "mean_drop_end": float(np.mean([item["drop_end"] for item in items])),
        "structural_by_horizon": dict(Counter(item["structural_horizon"] for item in items if item["structural"])),
        "median_structural_delay": (
            float(median([item["structural_delay"] for item in items if item["structural"]]))
            if any(item["structural"] for item in items) else None
        ),
        "verdict_delay_distribution": spread(verdicts),
        "alert_delay_distribution": spread(alerts),
        "by_size_band": {
            band: {"n": len(rows), "p_structural": sum(row["structural"] for row in rows) / len(rows),
                   "p_verdict": sum(row["verdict_delay"] is not None for row in rows) / len(rows),
                   "p_alert": sum(row["alert_delay"] is not None for row in rows) / len(rows),
                   "median_verdict_delay": delay(rows, "verdict_delay"),
                   "median_alert_delay": delay(rows, "alert_delay")}
            for band, rows in sorted(bands.items())
        },
        # windows whose untouched run has no deterioration verdict at all
        "quiet_base": {
            "n": len(quiet),
            "p_structural": sum(row["structural"] for row in quiet) / len(quiet) if quiet else None,
            "p_verdict": sum(row["verdict_delay"] is not None for row in quiet) / len(quiet) if quiet else None,
            "structural_in_month_0": sum(row["structural_delay"] == 0 for row in quiet),
        },
    }


# --------------------------------------------------------------------------
# receipt and entry point
# --------------------------------------------------------------------------


def check_status(raw: Mapping[str, Any]) -> str:
    """ok | warn | fail | info (measured, no verdict) of one raw check result."""
    if raw.get("pass") is False:
        return "fail"
    if raw.get("warning"):
        return "warn"
    return "ok" if raw.get("pass") is True else "info"


def _status(raw: Mapping[str, Any]) -> str:
    # the frozen bundle contract has no "warn": a warning reads as info and says so in its summary
    return {"ok": "pass", "fail": "fail"}.get(check_status(raw), "info")


def receipt_check(key: str, raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """One check in the shape of ``receipt.json`` of the bundle contract."""
    if not isinstance(raw, Mapping):
        return {"key": key, "title": TITLES.get(key, key), "status": "not_run", "summary": NOT_RUN, "metrics": []}
    check = {
        "key": key, "title": TITLES.get(key, key), "status": _status(raw),
        "summary": (str(raw.get("summary") or TITLES.get(key, key)))[:400],
        "metrics": list(raw.get("metrics") or [])[:24],
    }
    bars = [
        {"label": str(item["label"])[:40], "value": float(item["value"])}
        for item in raw.get("bars") or [] if str(item.get("label") or "")
    ]
    if bars:
        check["bars"] = bars
    return check


def build_receipt(scored: Scored, checks: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    """``receipt.json`` of the bundle contract from the scored result and the checks."""
    params = scored.params
    try:
        from .export import SIGNAL_WHY, ZERO_WEIGHT_SIGNALS
    except Exception:  # noqa: BLE001 - the receipt still names every signal
        SIGNAL_WHY, ZERO_WEIGHT_SIGNALS = {}, _ZERO_WEIGHT
    signals = [
        {"name": key, "label": PILLAR_LABELS[key], "weight": float(params.weights[key]),
         "why": SIGNAL_WHY.get(key, _SIGNAL_WHY)}
        for key in PILLAR_KEYS
    ]
    signals += [{"name": name, "label": label, "weight": 0.0, "why": why} for name, label, why in ZERO_WEIGHT_SIGNALS]
    abstentions = []
    for (kind, entity_id), items in _entities(scored.months).items():
        last = items[-1]
        if last.row.month != scored.last_month or not last.parts.abstained:
            continue
        if not (_ID_PATTERN.match(entity_id) and _ID_PATTERN.match(last.row.group_id)):
            continue
        reason = last.parts.abstain_reason or "abstained"
        hint = last.parts.unlock_hint or UNLOCK_HINTS.get(reason, "") or "Completar los datos de la entidad."
        abstentions.append({
            "entity_kind": kind, "entity_id": entity_id, "group_id": last.row.group_id,
            "month": f"{last.row.month:%Y-%m}", "reason": reason, "unlock": hint[:400],
        })
    abstentions.sort(key=lambda item: (item["entity_kind"] != "group", item["entity_id"]))
    return {
        "schema": BUNDLE_SCHEMA, "kind": "receipt", "engine_version": ENGINE_VERSION,
        "params_hash": str(params.sha256 or "unhashed"), "dataset_hash": str(scored.tables.dataset_hash or "unknown"),
        "signals": signals, "abstentions": abstentions,
        "checks": [receipt_check(key, checks.get(key)) for key in CHECK_KEYS],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, Path)):
        return str(value)
    return value


def run_checks(scored: Scored, *, quick: bool = False, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Every check on one ``Scored``; ``quick`` leaves out ``QUICK_SKIPPED`` and
    runs isolation, truncation, determinism and scale on a few groups."""
    few = pick_groups(scored, 12, seed=11) if quick else None
    plan: dict[str, Callable[[], dict[str, Any]]] = {
        "isolation": lambda: check_isolation(scored, n_groups=12 if quick else 60),
        "truncation": lambda: check_truncation(
            scored if not quick else score_core(subset_tables(scored.tables, few), scored.params),
            months=[_shift_month(scored.last_month, -6)] if quick else None,
        ),
        "additivity": lambda: check_additivity(scored),
        "scale": lambda: check_scale_invariance(scored, group_ids=few),
        "determinism": lambda: check_determinism(scored, group_ids=few),
        "ablation": lambda: paired_ablation(scored),
        "neutrality": lambda: neutrality(scored, draws=50 if quick else 200),
        "penalty_by_branch": lambda: penalty_by_branch(scored),
        "rank_stability": lambda: rank_stability(scored, draws=30 if quick else 200),
        "history_truncation": lambda: history_truncation(scored),
        "persistence": lambda: persistence(scored),
        "netting_placebo": lambda: netting_placebo(scored),
        "injection": lambda: injection_study(scored),
    }
    results: dict[str, Any] = {}
    for key in CHECK_KEYS:
        if quick and key in QUICK_SKIPPED:
            continue
        started = time.perf_counter()
        try:
            results[key] = plan[key]()
        except Exception as error:  # noqa: BLE001 - one broken check must not hide the others
            results[key] = {
                "pass": False, "error": f"{type(error).__name__}: {error}"[:300],
                "summary": f"La comprobación no pudo completarse: {type(error).__name__}.", "metrics": [],
            }
        results[key]["status"] = check_status(results[key])
        results[key]["seconds"] = round(time.perf_counter() - started, 2)
        if log is not None:
            log(f"{key}: {results[key]['status']} in {results[key]['seconds']}s")
    return results


def run_validation(
    input_dir: Path,
    params: Params | None = None,
    out_path: Path = DEFAULT_VALIDATION_PATH,
    *,
    cache_dir: Path | None = None,
    quick: bool = False,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Loads and scores ``input_dir`` once, runs every check and writes ``out_path``.

    Returns the written document: ``{dataset_hash, params_hash, engine_version,
    quick, runtime_seconds, status_counts, <check key>: result, checks: [...],
    receipt: {...}}``. Every result carries ``status`` ok | warn | fail | info;
    ``checks`` and ``receipt`` follow ``receipt.json`` of the bundle contract,
    whose status enum is pass | fail | info | not_run (a warning reads as info).
    """
    started = time.perf_counter()
    params = params if params is not None else load_params()
    tables = io.load_tables(Path(input_dir), Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR)
    scored = score_core(tables, params)
    if log is not None:
        log(f"scored {scored.frame.height} entity-months in {time.perf_counter() - started:.1f}s")
    results = run_checks(scored, quick=quick, log=log)
    receipt = build_receipt(scored, results)
    counts = Counter(item["status"] for item in results.values())
    document = _jsonable({
        "dataset_hash": tables.dataset_hash, "params_hash": params.sha256, "engine_version": ENGINE_VERSION,
        "quick": quick, "runtime_seconds": round(time.perf_counter() - started, 1),
        "status_counts": {name: counts.get(name, 0) for name in ("ok", "warn", "fail", "info")},
        **results, "checks": receipt["checks"], "receipt": receipt,
    })
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return document


__all__ = [
    "CHECK_KEYS",
    "DEFAULT_VALIDATION_PATH",
    "INJECTION_KINDS",
    "NEUTRALITY_DIMENSIONS",
    "Scored",
    "build_receipt",
    "check_additivity",
    "check_determinism",
    "check_isolation",
    "check_scale_invariance",
    "check_truncation",
    "compare_scores",
    "conditional_rates",
    "core_frame",
    "eta_squared",
    "excess_eta_squared",
    "group_attributes",
    "history_truncation",
    "inject",
    "injection_study",
    "netting_placebo",
    "neutrality",
    "paired_ablation",
    "penalty_by_branch",
    "persistence",
    "pick_groups",
    "rank_stability",
    "receipt_check",
    "run_checks",
    "run_validation",
    "score_core",
    "shuffle_tables",
    "spearman",
    "subset_tables",
    "tail_tables",
    "truncate_tables",
]
