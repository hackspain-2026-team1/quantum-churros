"""Frozen reference parameters: load, validate, canonical dump and sha256.

``params/reference_v1.json`` is the only cohort-dependent input of the engine.
The hash is taken over the canonical dump of the parsed ``Params`` (without
the ``sha256`` field), so it does not depend on JSON formatting.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
import types
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import contracts
from .contracts import (
    ANCHOR_KEYS,
    BAND_KEYS,
    DASH_LABELS,
    FLOW_CLASSES,
    PILLAR_KEYS,
    SIZE_BANDS,
    Anchors,
    Params,
)

PARAMS_ENV = "XRAY_PARAMS"
DEFAULT_PARAMS_PATH = (
    Path(__file__).resolve().parents[3] / "params" / "reference_v1.json"
)


class ParamsError(ValueError):
    """Invalid, incomplete or tampered parameters."""


def default_params_path() -> Path:
    """``$XRAY_PARAMS`` when set, else ``<repo>/params/reference_v1.json``."""
    override = os.environ.get(PARAMS_ENV)
    return Path(override) if override else DEFAULT_PARAMS_PATH


def _build(annotation: Any, value: Any, where: str) -> Any:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        options = [item for item in typing.get_args(annotation) if item is not type(None)]
        if value is None:
            return None
        return _build(options[0], value, where)
    if origin is typing.Literal:
        if value not in typing.get_args(annotation):
            raise ParamsError(f"{where}: {value!r} not in {typing.get_args(annotation)}")
        return value
    if annotation is Anchors:
        return Anchors(tuple((float(x), float(y)) for x, y in value))
    if dataclasses.is_dataclass(annotation):
        return _build_dataclass(annotation, value, where)
    if origin is tuple:
        args = typing.get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_build(args[0], item, f"{where}[]") for item in value)
        if len(args) != len(value):
            raise ParamsError(f"{where}: expected {len(args)} values")
        return tuple(_build(arg, item, where) for arg, item in zip(args, value))
    if origin in (Mapping, dict):
        item_type = typing.get_args(annotation)[1]
        return {str(key): _build(item_type, item, f"{where}.{key}") for key, item in value.items()}
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParamsError(f"{where}: expected a number, got {value!r}")
        return float(value)
    if annotation in (int, str, bool):
        if type(value) is not annotation:
            raise ParamsError(f"{where}: expected {annotation.__name__}, got {value!r}")
        return value
    raise ParamsError(f"{where}: unsupported annotation {annotation!r}")


def _build_dataclass(cls: Any, value: Any, where: str) -> Any:
    if not isinstance(value, Mapping):
        raise ParamsError(f"{where}: expected an object")
    hints = typing.get_type_hints(cls, vars(contracts))
    names = [item.name for item in dataclasses.fields(cls)]
    unknown = sorted(set(value) - set(names))
    missing = [name for name in names if name not in value]
    if unknown or missing:
        raise ParamsError(f"{where}: unknown keys {unknown}, missing keys {missing}")
    return cls(**{name: _build(hints[name], value[name], f"{where}.{name}") for name in names})


def _plain(value: Any) -> Any:
    if isinstance(value, Anchors):
        return [[x, y] for x, y in value.points]
    if dataclasses.is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _pretty(value: Any, level: int = 0) -> str:
    # objects one key per line (sorted); arrays of scalars or pairs inline
    pad = "  " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{pad}{json.dumps(key, ensure_ascii=False)}: {_pretty(item, level + 1)}"
            for key, item in sorted(value.items())
        ]
        return "{\n" + ",\n".join(items) + "\n" + "  " * level + "}"
    if isinstance(value, list) and any(isinstance(item, dict) for item in value):
        items = [pad + _pretty(item, level + 1) for item in value]
        return "[\n" + ",\n".join(items) + "\n" + "  " * level + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def params_from_dict(data: Mapping[str, Any]) -> Params:
    """Strict parse: unknown or missing keys raise ``ParamsError``; then validate."""
    params = _build_dataclass(Params, data, "params")
    validate_params(params)
    return params


def params_to_dict(params: Params) -> dict[str, Any]:
    return _plain(params)


def canonical_dump(params: Params) -> str:
    """Deterministic JSON of everything except ``sha256``."""
    data = params_to_dict(params)
    data.pop("sha256")
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def params_hash(params: Params) -> str:
    return hashlib.sha256(canonical_dump(params).encode("utf-8")).hexdigest()


def _check_anchors(name: str, anchors: Anchors, low: float, high: float) -> None:
    points = anchors.points
    if len(points) < 2:
        raise ParamsError(f"{name}: at least two anchor points are required")
    if any(x1 <= x0 for (x0, _), (x1, _) in zip(points, points[1:])):
        raise ParamsError(f"{name}: anchor x values must be strictly increasing")
    if any(not low <= y <= high for _, y in points):
        raise ParamsError(f"{name}: anchor y values must lie in [{low}, {high}]")


def _check_share(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ParamsError(f"{name} must lie in [0, 1]")


def validate_params(params: Params) -> None:
    """Structural checks only; raises ``ParamsError`` on the first violation."""
    if set(params.weights) != set(PILLAR_KEYS):
        raise ParamsError(f"weights must define exactly {PILLAR_KEYS}")
    if any(weight <= 0 for weight in params.weights.values()):
        raise ParamsError("weights must be positive")
    if abs(sum(params.weights.values()) - 1.0) > 1e-9:
        raise ParamsError("weights must sum to 1")
    if set(params.anchors) != set(ANCHOR_KEYS):
        raise ParamsError(f"anchors must define exactly {ANCHOR_KEYS}")
    for key, anchors in params.anchors.items():
        _check_anchors(f"anchors.{key}", anchors, 0.0, 100.0)

    bounds = params.size_bands.upper_bounds_eur
    if len(bounds) != len(SIZE_BANDS) - 1 or any(b <= a for a, b in zip((0.0, *bounds), bounds)):
        raise ParamsError("size_bands.upper_bounds_eur: one increasing positive bound per band but the last")
    if params.size_bands.window_months < 1 or params.size_bands.hold_months < 1:
        raise ParamsError("size_bands: window_months and hold_months must be positive")

    liquidity = params.liquidity
    if abs(liquidity.month_end_weight + liquidity.intra_min_weight - 1.0) > 1e-9:
        raise ParamsError("liquidity weights must sum to 1")
    if not 1 <= liquidity.outflow_window_months <= liquidity.outflow_fallback_months:
        raise ParamsError("liquidity: outflow windows must satisfy 1 <= window <= fallback")
    if set(liquidity.band_anchors) != set(SIZE_BANDS):
        raise ParamsError(f"liquidity.band_anchors must define exactly {SIZE_BANDS}")
    quantiles, scores = liquidity.band_quantiles, liquidity.band_scores
    if len(quantiles) != len(scores) or not quantiles:
        raise ParamsError("liquidity: one band score per band quantile")
    if any(b <= a for a, b in zip(quantiles, quantiles[1:])) or not 0 < quantiles[0] <= quantiles[-1] < 1:
        raise ParamsError("liquidity.band_quantiles must be strictly increasing inside (0, 1)")
    for key, anchors in liquidity.band_anchors.items():
        _check_anchors(f"liquidity.band_anchors.{key}", anchors, 0.0, 100.0)
        if tuple(y for _, y in anchors.points) != (0.0, *scores) or anchors.points[0][0] != 0.0:
            raise ParamsError(f"liquidity.band_anchors.{key}: (0, 0) followed by one point per band score")

    invoices = params.invoices
    if invoices.window_days < 1 or invoices.clip_days[0] >= invoices.clip_days[1]:
        raise ParamsError("invoices: positive window and clip low below clip high")
    if invoices.min_invoices < 1 or invoices.min_effective_n <= 0:
        raise ParamsError("invoices: gates must be positive")
    _check_share("invoices.stamped_share_max", invoices.stamped_share_max)
    _check_share("invoices.zero_terms_stamped_share", invoices.zero_terms_stamped_share)
    _check_share("invoices.never_settles_open_share", invoices.never_settles_open_share)
    if invoices.never_settles_min_aged < 1:
        raise ParamsError("invoices.never_settles_min_aged must be positive")

    activity = params.activity
    if not 1 <= activity.coverage_min_months <= activity.coverage_window_months:
        raise ParamsError("activity: coverage_min_months must lie in [1, coverage_window_months]")
    if not 1 <= activity.min_prior_months <= activity.prior_months or activity.recent_months < 1:
        raise ParamsError("activity: min_prior_months must lie in [1, prior_months]")
    if not 1 <= params.debt.min_months <= params.debt.window_months:
        raise ParamsError("debt: min_months must lie in [1, window_months]")
    if params.robust.monthly_winsor_multiple < 1:
        raise ParamsError("robust.monthly_winsor_multiple must be at least 1")

    if params.penalty.lam < 0 or not 0 <= params.penalty.tau <= 100:
        raise ParamsError("penalty: lam >= 0 and tau in [0, 100] (points)")
    caps = params.caps
    if any(not 0 <= value <= 100 for value in (caps.negative_liquidity_ceiling, caps.weak_payments_ceiling)):
        raise ParamsError("caps: ceilings must lie in [0, 100]")
    if not 1 <= caps.negative_liquidity_min_months <= caps.negative_liquidity_window_months:
        raise ParamsError("caps: negative_liquidity_min_months must lie in [1, window]")
    _check_share("caps.negative_liquidity_max_no_anchor_share", caps.negative_liquidity_max_no_anchor_share)
    if set(params.bands) != set(BAND_KEYS):
        raise ParamsError(f"bands must define exactly {BAND_KEYS}")
    minimums = [params.bands[key] for key in BAND_KEYS]
    if minimums[0] != 0.0 or any(b <= a for a, b in zip(minimums, minimums[1:])) or minimums[-1] > 100:
        raise ParamsError("bands: minimums start at 0 and increase strictly")

    feed = params.live_feed
    if not 0 < feed.threshold <= 1:
        raise ParamsError("live_feed.threshold must lie in (0, 1]")
    if not feed.base_from_months >= feed.base_to_months > feed.recent_months - 1 >= 0:
        raise ParamsError("live_feed: the base window must end before the recent months")
    confidence = params.confidence
    for key in (
        "history",
        "coverage",
        "quality_dash",
        "quality_fx_excluded",
        "quality_orphan",
        "quality_no_cash_anchor",
    ):
        _check_anchors(f"confidence.{key}", getattr(confidence, key), 0.0, 1.0)
    _check_share("confidence.limit_assumed_constant_factor", confidence.limit_assumed_constant_factor)
    _check_share("confidence.stale_feed_factor", confidence.stale_feed_factor)
    if not 0 < confidence.label_medium_min < confidence.label_high_min <= 1:
        raise ParamsError("confidence labels: 0 < label_medium_min < label_high_min <= 1")
    if params.abstention.min_months_observed < 1:
        raise ParamsError("abstention.min_months_observed must be positive")
    if not params.abstention.bank_pillars or set(params.abstention.bank_pillars) - set(PILLAR_KEYS):
        raise ParamsError("abstention.bank_pillars must be pillar keys")

    trajectory = params.trajectory
    if trajectory.horizon_months < 1 or trajectory.min_scored_months <= trajectory.horizon_months:
        raise ParamsError("trajectory: min_scored_months must exceed horizon_months")
    if trajectory.sigma_floor <= 0 or trajectory.min_delta_points <= 0:
        raise ParamsError("trajectory: thresholds must be positive")
    if not 3 <= trajectory.long_min_months <= trajectory.long_horizon:
        raise ParamsError("trajectory: long_min_months must lie in [3, long_horizon]")
    if trajectory.long_threshold <= 0 or trajectory.long_sigma_mult < 0:
        raise ParamsError("trajectory: long_threshold > 0 and long_sigma_mult >= 0")
    _check_share("trajectory.perimeter_shift_share", trajectory.perimeter_shift_share)
    _check_share("trajectory.bump_revert_fraction", trajectory.bump_revert_fraction)
    _check_share("profile.concentration_top1_share", params.profile.concentration_top1_share)
    if not 1 <= params.profile.concentration_min_months <= params.profile.concentration_window_months:
        raise ParamsError("profile: concentration_min_months must lie in [1, window]")

    if set(params.reference.medians) != set(PILLAR_KEYS):
        raise ParamsError("reference.medians must define every pillar")
    if any(not 0 <= value <= 100 for value in params.reference.medians.values()):
        raise ParamsError("reference.medians must lie in [0, 100]")
    if params.fx.rates.get(params.fx.base) != 1.0:
        raise ParamsError("fx: the base currency must have rate 1")
    if any(rate <= 0 for rate in params.fx.rates.values()):
        raise ParamsError("fx: rates must be positive")
    mirror = params.mirror
    if mirror.min_amount_eur < 0 or not 0 <= mirror.max_day_gap <= mirror.weekend_bridge_day_gap:
        raise ParamsError("mirror: min_amount_eur >= 0 and max_day_gap <= weekend_bridge_day_gap")
    if any(not 0 <= day <= 6 for day in mirror.weekend_bridge_weekdays) or mirror.reversal_max_day_gap < 0:
        raise ParamsError("mirror: weekdays follow date.weekday() and gaps are not negative")
    seen: set[str] = set()
    for rule in params.dash_rules:
        if rule.id in seen:
            raise ParamsError(f"dash_rules: duplicated id {rule.id}")
        seen.add(rule.id)
        if rule.flow_class not in FLOW_CLASSES:
            raise ParamsError(f"dash_rules.{rule.id}: unknown flow_class {rule.flow_class}")
        if rule.label not in DASH_LABELS:
            raise ParamsError(f"dash_rules.{rule.id}: unknown label {rule.label}")
        if rule.precision is not None and not 0 <= rule.precision <= 1:
            raise ParamsError(f"dash_rules.{rule.id}: precision must lie in [0, 1]")
        for pattern in (rule.pattern, rule.exclude):
            if pattern is None:
                continue
            try:
                re.compile(pattern)
            except re.error as error:
                raise ParamsError(f"dash_rules.{rule.id}: bad regex: {error}") from error


def load_params(path: Path | None = None, *, verify: bool = True) -> Params:
    """Read and validate a params file.

    With ``verify`` (default) a stored ``sha256`` that differs from the hash of
    the content raises ``ParamsError``: scoring never runs on edited params.
    """
    source = Path(path) if path is not None else default_params_path()
    if not source.is_file():
        raise ParamsError(f"Params file not found: {source}")
    params = params_from_dict(json.loads(source.read_text(encoding="utf-8")))
    if verify and params.sha256 != params_hash(params):
        raise ParamsError(
            f"{source}: sha256 does not match its content; re-stamp it with "
            "`python -m xray_engine.params <path>` or run fit-reference"
        )
    return params


def write_params(params: Params, path: Path) -> Params:
    """Validate, stamp the sha256 and write pretty JSON. Returns the stamped params."""
    validate_params(params)
    stamped = dataclasses.replace(params, sha256=params_hash(params))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_pretty(params_to_dict(stamped)) + "\n", encoding="utf-8")
    return stamped


def _restamp(arguments: list[str]) -> None:
    target = Path(arguments[0]) if arguments else default_params_path()
    stamped = write_params(load_params(target, verify=False), target)
    print(f"{target}: sha256 {stamped.sha256}")


if __name__ == "__main__":
    _restamp(sys.argv[1:])
