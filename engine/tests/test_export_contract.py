"""The static bundle honours ``contracts/xray-export-v1.schema.json``.

Two subjects: the synthetic fixture the web app is built against (checked now)
and the output of ``export_bundle`` (pending until ``export.py`` exists).
"""

from __future__ import annotations

import csv
import json
import shutil
import typing
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from bundle_contract import (
    ENTITY_FOLDERS,
    FIXTURE_DIR,
    SINGLE_FILES,
    bundle_id,
    check_bundle,
    identity_gap,
    load_schema,
)
from xray_engine import contracts
from xray_engine.contracts import IndustryClassification
from xray_engine.export import BUNDLE_SCHEMA, export_bundle
from xray_engine.scoring import score_dataset

pending = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="export.py is a stub"
)


def _entity_files(bundle_dir: Path) -> list[tuple[str, dict]]:
    """(entity_kind, file content) of every group and company file."""
    found = []
    for folder, kind in (("groups", "group"), ("companies", "company")):
        for path in sorted((bundle_dir / folder).glob("*.json")):
            found.append((kind, json.loads(path.read_text(encoding="utf-8"))))
    return found


def _assert_integer_identity(bundle_dir: Path) -> int:
    checked = 0
    for _, entity in _entity_files(bundle_dir):
        for entry in entity["months"]:
            parts = [entry["shown"], entry["base"], entry["penalty"], entry["cap"]["amount"]]
            parts += [pillar["contrib"] for pillar in entry["pillars"]]
            assert all(type(value) is int for value in parts), (entity["id"], entry["month"])
            assert identity_gap(entry) == 0, (entity["id"], entry["month"])
            checked += 1
    return checked


# --------------------------------------------------------------------------
# schema and fixture
# --------------------------------------------------------------------------


def test_schema_has_one_definition_per_bundle_file() -> None:
    schema = load_schema()
    kinds = [*SINGLE_FILES.values(), *ENTITY_FOLDERS.values()]
    assert sorted(option["$ref"] for option in schema["oneOf"]) == sorted(
        f"#/$defs/{kind}" for kind in kinds
    )
    for kind in kinds:
        properties = schema["$defs"][kind]["properties"]
        assert properties["schema"] == {"const": BUNDLE_SCHEMA}
        assert properties["kind"] == {"const": kind}
        assert schema["$defs"][kind]["additionalProperties"] is False


def test_schema_vocabularies_follow_the_engine_contracts() -> None:
    defs = load_schema()["$defs"]
    assert tuple(defs["pillarKey"]["enum"]) == contracts.PILLAR_KEYS
    assert tuple(defs["nature"]["enum"]) == typing.get_args(contracts.Nature)
    assert set(typing.get_args(contracts.Direction)) <= set(defs["direction"]["enum"])
    assert tuple(defs["entityKind"]["enum"]) == typing.get_args(contracts.EntityKind)
    alert = defs["alert"]["properties"]
    assert tuple(alert["kind"]["enum"]) == typing.get_args(contracts.AlertKind)
    assert tuple(alert["state"]["enum"]) == typing.get_args(contracts.AlertState)
    evidence_fields = set(defs["evidenceRow"]["properties"]) - {"pillar"}
    assert evidence_fields == {item.name for item in fields(contracts.Evidence)}
    assert defs["evidenceRow"]["additionalProperties"] is False


def test_fixture_bundle_follows_the_contract() -> None:
    assert check_bundle(FIXTURE_DIR) == []
    assert _assert_integer_identity(FIXTURE_DIR) > 100
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    alerts = json.loads((FIXTURE_DIR / "alerts.json").read_text(encoding="utf-8"))["alerts"]
    assert manifest["counts"] == {"groups": 3, "companies": 5, "alerts": len(alerts)}
    assert len(manifest["months"]) == 24
    assert {alert["state"] for alert in alerts} == {"fired", "suppressed", "abstained"}


def _break_identity(root: Path) -> None:
    path = root / "groups" / "GROUP_T001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["months"][-1]["pillars"][0]["contrib"] += 1
    path.write_text(json.dumps(data), encoding="utf-8")


def _float_tenths(root: Path) -> None:
    path = root / "companies" / "COMP_T001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["months"][0]["base"] += 0.5
    path.write_text(json.dumps(data), encoding="utf-8")


def _raw_description(root: Path) -> None:
    path = root / "evidence" / "GROUP_T001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["months"][0]["rows"][0]["description"] = "TRANSFERENCIA DE [COMPANY] FRA [NUM]"
    path.write_text(json.dumps(data), encoding="utf-8")


def _fired_inside_abstention(root: Path) -> None:
    path = root / "alerts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    alert = next(item for item in data["alerts"] if item["state"] == "abstained")
    alert["state"], alert["suppressed_by"] = "fired", None
    path.write_text(json.dumps(data), encoding="utf-8")


def _stale_portfolio(root: Path) -> None:
    path = root / "portfolio.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["groups"][0]["shown"][-1] -= 1
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_break_identity, "misses shown by 1 tenths"),
        (_float_tenths, "expected integer"),
        (_raw_description, "unexpected property 'description'"),
        (_fired_inside_abstention, "an abstained month cannot fire"),
        (_stale_portfolio, "shown is not the projection"),
    ],
)
def test_checker_rejects_a_broken_bundle(tmp_path, mutate, expected) -> None:
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIR, root)
    mutate(root)
    errors = check_bundle(root)
    assert any(expected in item for item in errors), errors


def test_bundle_id_covers_every_other_file(tmp_path) -> None:
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURE_DIR, root)
    before = bundle_id(root)
    manifest = root / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert bundle_id(root) == before
    receipt = root / "receipt.json"
    receipt.write_text(receipt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert bundle_id(root) != before
    assert "manifest.json: bundle_id does not match the files" in check_bundle(root)


# --------------------------------------------------------------------------
# engine output
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def exported(synthetic, params, tmp_path_factory) -> SimpleNamespace:
    root = tmp_path_factory.mktemp("export-contract")
    company = synthetic.company_ids[0]
    industry = {
        company: IndustryClassification(
            entity_id=company, industry_slug="wholesale", industry_label="Distribución mayorista",
            confidence=0.6, source="override", reason="Caso de prueba.",
            classifier_version="test", dataset_hash="test",
        )
    }
    result = score_dataset(
        synthetic.path, params, cache_dir=root / "cache", industry_override=industry
    )
    manifest = export_bundle(result, root / "bundle")
    return SimpleNamespace(result=result, manifest=manifest, path=root / "bundle", company=company)


@pending
def test_export_validates_against_the_schema(exported) -> None:
    assert check_bundle(exported.path) == []
    written = json.loads((exported.path / "manifest.json").read_text(encoding="utf-8"))
    assert written == exported.manifest
    assert written["schema"] == BUNDLE_SCHEMA
    assert written["params_hash"] == exported.result.params.sha256
    assert written["dataset_hash"] == exported.result.dataset_hash
    assert written["engine_version"] == contracts.ENGINE_VERSION
    company = json.loads(
        (exported.path / "companies" / f"{exported.company}.json").read_text(encoding="utf-8")
    )
    assert company["context"]["industry"]["slug"] == "wholesale"


@pending
def test_integer_identity_holds_for_every_group_month(exported) -> None:
    checked = _assert_integer_identity(exported.path)
    snapshots = exported.result.snapshots
    assert checked == snapshots.height
    shown = {
        (kind, entity["id"], entry["month"]): entry["shown"]
        for kind, entity in _entity_files(exported.path)
        for entry in entity["months"]
    }
    for row in snapshots.select("entity_kind", "entity_id", "month", "score").iter_rows(named=True):
        key = (row["entity_kind"], row["entity_id"], row["month"].strftime("%Y-%m"))
        assert abs(shown[key] - row["score"] * 10) <= 0.5 + 1e-6, key
    group_months = sum(1 for kind, _, _ in shown if kind == "group")
    assert group_months == snapshots.filter(pl.col("entity_kind") == "group").height > 0


@pending
def test_export_never_leaks_a_raw_description(exported, synthetic) -> None:
    with (synthetic.path / "transactions.csv").open(newline="", encoding="utf-8") as handle:
        descriptions = {
            " ".join(row["description"].split())
            for row in csv.DictReader(line.replace("\x00", "") for line in handle)
        }
    descriptions = {text for text in descriptions if len(text) >= 12}
    assert descriptions
    for path in sorted(exported.path.rglob("*.json")):
        text = " ".join(path.read_text(encoding="utf-8").split())
        leaked = [item for item in descriptions if item in text]
        assert not leaked, (path.name, leaked[:3])


@pending
@pytest.mark.dataset
def test_real_export_follows_the_contract(real_data_dir, params, tmp_path) -> None:
    result = score_dataset(real_data_dir, params, cache_dir=tmp_path / "cache")
    export_bundle(result, tmp_path / "bundle")
    assert check_bundle(tmp_path / "bundle") == []
    assert _assert_integer_identity(tmp_path / "bundle") == result.snapshots.height
