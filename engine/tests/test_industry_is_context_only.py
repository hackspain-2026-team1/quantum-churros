"""The industry archetype is context on the profile card, never a score input."""

from __future__ import annotations

import ast
import dataclasses
import random
from pathlib import Path

import pytest
import xray_engine
from xray_engine.contracts import (
    PANEL_COLUMNS,
    IndustryClassification,
    PanelRow,
    Params,
    PillarResult,
    ScoreParts,
    Trajectory,
)
from xray_engine.scoring import score_dataset

PACKAGE_DIR = Path(xray_engine.__file__).parent
PURE_MODULES = ("pillars", "aggregate", "trajectory", "alerts", "actions")
ALLOWED_ENGINE_IMPORTS = {"contracts", "pillars", "aggregate", "trajectory"}
FORBIDDEN_LIBRARIES = {
    "polars", "pandas", "pyarrow", "numpy", "os", "pathlib", "io", "csv", "json", "sqlite3",
    "shutil", "glob", "urllib", "requests", "subprocess",
}


def _imports(module: str) -> tuple[set[str], set[str]]:
    """(top-level external libraries, engine modules) imported by a module."""
    tree = ast.parse((PACKAGE_DIR / f"{module}.py").read_text(encoding="utf-8"))
    external: set[str] = set()
    internal: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                (internal if root == "xray_engine" else external).add(
                    alias.name.split(".")[1] if root == "xray_engine" and "." in alias.name else root
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: from .x import y / from . import x
                names = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                internal.update(names)
            elif node.module and node.module.split(".")[0] == "xray_engine":
                parts = node.module.split(".")
                internal.update([parts[1]] if len(parts) > 1 else [a.name for a in node.names])
            elif node.module:
                external.add(node.module.split(".")[0])
    return external, internal


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_core_imports_no_frames_no_io_no_industry(module) -> None:
    external, internal = _imports(module)
    assert not external & FORBIDDEN_LIBRARIES, external & FORBIDDEN_LIBRARIES
    assert internal <= ALLOWED_ENGINE_IMPORTS, internal - ALLOWED_ENGINE_IMPORTS
    tree = ast.parse((PACKAGE_DIR / f"{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}
        names = [
            getattr(node, "id", None), getattr(node, "attr", None), getattr(node, "arg", None),
            getattr(node, "name", None),
        ]
        assert not any("industry" in str(name).lower() for name in names if name), module


def _field_names(cls: type) -> set[str]:
    if not dataclasses.is_dataclass(cls):
        return set()
    return {item.name for item in dataclasses.fields(cls)}


def test_no_score_input_mentions_industry(params) -> None:
    carriers = [PanelRow, PillarResult, ScoreParts, Trajectory, Params]
    carriers += [type(getattr(params, item.name)) for item in dataclasses.fields(Params)]
    for cls in carriers:
        assert not [name for name in _field_names(cls) if "industry" in name or "sector" in name], cls
    assert not [name for name in PANEL_COLUMNS if "industry" in name or "sector" in name]


def test_permuting_industry_labels_changes_no_score(synthetic, params, tmp_path) -> None:
    base = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache")
    labels = ["software", "manufacturing", "healthcare", "energy_utilities"]
    rng = random.Random(41)
    shuffled = {
        company_id: IndustryClassification(
            entity_id=company_id, industry_slug=(slug := rng.choice(labels)), industry_label=slug,
            confidence=0.9, source="override", reason="permutation test",
            classifier_version="test", dataset_hash=base.dataset_hash,
        )
        for company_id in synthetic.company_ids
    }
    permuted = score_dataset(
        synthetic.path, params, cache_dir=tmp_path / "cache", industry_override=shuffled
    )
    assert permuted.snapshots.equals(base.snapshots)
    assert permuted.panel.equals(base.panel)
    assert permuted.alerts == base.alerts
    company = synthetic.company_ids[0]
    assert permuted.profiles[company].context["industry"]["slug"] == shuffled[company].industry_slug
    without_context = lambda card: dataclasses.replace(card, context={})  # noqa: E731
    assert {key: without_context(card) for key, card in permuted.profiles.items()} == {
        key: without_context(card) for key, card in base.profiles.items()
    }
