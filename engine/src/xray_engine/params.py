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
    DASH_LABELS,
    PILLAR_KEYS,
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
    confidence = params.confidence
    for key in (
        "history",
        "coverage",
        "quality_uncategorised",
        "quality_fx_excluded",
        "quality_cash_anchor",
    ):
        _check_anchors(f"confidence.{key}", getattr(confidence, key), 0.0, 1.0)
    if not 0 < confidence.abstain_below < 1 or not 0 <= confidence.stale_feed_factor <= 1:
        raise ParamsError("confidence thresholds must lie in (0, 1)")
    if set(params.reference.medians) != set(PILLAR_KEYS):
        raise ParamsError("reference.medians must define every pillar")
    if any(not 0 <= value <= 100 for value in params.reference.medians.values()):
        raise ParamsError("reference.medians must lie in [0, 100]")
    if params.penalty.lam < 0 or not 0 <= params.penalty.tau <= 100:
        raise ParamsError("penalty: lam >= 0 and tau in [0, 100] (points)")
    if not 0 < params.ewma_alpha <= 1:
        raise ParamsError("ewma_alpha must lie in (0, 1]")
    caps = params.caps
    ceilings = (
        caps.negative_liquidity_ceiling,
        caps.lines_drawn_ceiling,
        caps.weak_pillar_ceiling,
    )
    if any(not 0 <= value <= 100 for value in ceilings):
        raise ParamsError("caps: ceilings must lie in [0, 100]")
    if set(caps.weak_pillars) - set(PILLAR_KEYS):
        raise ParamsError("caps.weak_pillars must be pillar keys")
    if not 0 < params.live_feed.threshold <= 1:
        raise ParamsError("live_feed.threshold must lie in (0, 1]")
    liquidity = params.liquidity
    if abs(liquidity.month_end_weight + liquidity.intra_min_weight - 1.0) > 1e-9:
        raise ParamsError("liquidity weights must sum to 1")
    if abs(params.debt.dscr_weight + params.debt.utilisation_weight - 1.0) > 1e-9:
        raise ParamsError("debt weights must sum to 1")
    if set(params.invoices.prior_days) != {"payments", "collections"}:
        raise ParamsError("invoices.prior_days must define payments and collections")
    if params.trajectory.structural_required_pillar not in PILLAR_KEYS:
        raise ParamsError("trajectory.structural_required_pillar must be a pillar key")
    if params.fx.rates.get(params.fx.base) != 1.0:
        raise ParamsError("fx: the base currency must have rate 1")
    if any(rate <= 0 for rate in params.fx.rates.values()):
        raise ParamsError("fx: rates must be positive")
    factors = params.seasonality.month_factors
    if len(factors) != 12 or any(factor <= 0 for factor in factors):
        raise ParamsError("seasonality.month_factors: 12 positive values")
    edges = params.psi.edges
    if len(edges) < 2 or any(b <= a for a, b in zip(edges, edges[1:])):
        raise ParamsError("psi.edges must be strictly increasing")
    if any(len(shares) != len(edges) - 1 for shares in params.psi.reference.values()):
        raise ParamsError("psi.reference: one share per bin")
    if any(low >= high for low, high in params.winsor.values()):
        raise ParamsError("winsor: low must be below high")
    if 0 not in params.mirror.day_offsets:
        raise ParamsError("mirror.day_offsets must include 0")
    seen: set[str] = set()
    for rule in params.dash_rules:
        if rule.id in seen:
            raise ParamsError(f"dash_rules: duplicated id {rule.id}")
        seen.add(rule.id)
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
