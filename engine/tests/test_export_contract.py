"""The static bundle honours ``contracts/xray-export-v1.schema.json``.

Two subjects: the synthetic fixture the web app is built against and the
output of ``export_bundle`` on the synthetic dataset.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
import typing
from dataclasses import fields
from datetime import date
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
from typer.testing import CliRunner
from xray_engine import contracts
from xray_engine.alerts import build_alerts
from xray_engine.cli import app
from xray_engine.contracts import IndustryClassification
from xray_engine.export import (
    BUNDLE_SCHEMA,
    TRUTH_TEXTS,
    export_bundle,
    export_from_result,
    round_preserving_sum,
)
from xray_engine.scoring import score_dataset, score_entity


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


def test_a_horizon_conflict_is_told_in_the_evidence(exported) -> None:
    from dataclasses import replace

    from xray_engine import export as export_module

    month = next(
        item for item in exported.result.months
        if item.trajectory.available and not item.parts.abstained and item.trajectory.drift_points is not None
    )
    agreed = replace(month.trajectory, direction="stable", nature=None, horizon=None, drift_call=None)
    assert not any("todavía apunta" in fact["label"] for fact in export_module._entity_facts(replace(month, trajectory=agreed)))
    rebound = replace(
        month.trajectory, direction="improving", nature="shock_pending", shock_pending=True, horizon="short",
        drift_points=-33.0, drift_months=12, drift_call="deteriorating",
    )
    facts = export_module._entity_facts(replace(month, trajectory=rebound))
    told = [fact for fact in facts if "todavía apunta a la baja" in fact["label"]]
    assert len(told) == 1 and told[0]["pillar"] is None and len(told[0]["label"]) <= 120
    assert "12 meses" in told[0]["label"] and "-33,0" in told[0]["label"]


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


@pytest.mark.dataset
def test_real_export_follows_the_contract(real_data_dir, params, tmp_path) -> None:
    result = score_dataset(real_data_dir, params, cache_dir=tmp_path / "cache")
    export_bundle(result, tmp_path / "bundle")
    assert check_bundle(tmp_path / "bundle") == []
    assert _assert_integer_identity(tmp_path / "bundle") == result.snapshots.height


# --------------------------------------------------------------------------
# rounding, determinism, glossary, receipt
# --------------------------------------------------------------------------


def test_round_preserving_sum_keeps_the_total_and_stays_within_one_unit() -> None:
    import random

    assert round_preserving_sum([], 0.0) == []
    assert round_preserving_sum([61.0, 0.0, -0.0], 61.0) == [610, 0, 0]
    assert round_preserving_sum([0.33, 0.33, 0.34], 1.0) == [3, 3, 4]
    # floors 644, -83, -24, -60, 0 miss 2 tenths: they go to the remainders .7 and .6
    assert round_preserving_sum([64.43, -8.26, -2.34, -5.93, 0.0], 47.9) == [644, -83, -23, -59, 0]
    rng = random.Random(7)
    for _ in range(2000):
        parts = [rng.uniform(40, 80)] + [rng.uniform(-15, 15) for _ in range(rng.randint(0, 5))]
        parts += [-rng.choice([0.0, rng.uniform(0, 22)]), -rng.choice([0.0, rng.uniform(0, 30)])]
        total = sum(parts)
        rounded = round_preserving_sum(parts, total)
        assert all(type(value) is int for value in rounded)
        assert sum(rounded) == round(total * 10)
        assert all(abs(value - part * 10) < 1 for value, part in zip(rounded, parts))
        assert rounded[-1] <= 0 and rounded[-2] <= 0
        assert [value for value, part in zip(rounded, parts) if part == 0] in ([], [0], [0, 0])


def test_bundle_id_is_deterministic_across_two_exports(exported, tmp_path) -> None:
    again = export_bundle(exported.result, tmp_path / "again")
    assert again["bundle_id"] == exported.manifest["bundle_id"] == bundle_id(tmp_path / "again")
    first = {p.relative_to(exported.path).as_posix(): p.read_bytes() for p in exported.path.rglob("*.json")}
    second = {p.relative_to(tmp_path / "again").as_posix(): p.read_bytes() for p in (tmp_path / "again").rglob("*.json")}
    assert first == second
    # exporting over a previous bundle leaves no stale file behind
    (tmp_path / "again" / "groups" / "GROUP_STALE.json").write_text("{}", encoding="utf-8")
    assert export_bundle(exported.result, tmp_path / "again")["bundle_id"] == again["bundle_id"]
    assert check_bundle(tmp_path / "again") == []
    # generated_at is an input, never the clock; it does not enter the bundle id
    stamped = export_bundle(exported.result, tmp_path / "stamped", generated_at="2026-09-19T10:00:00Z")
    assert stamped["generated_at"] == "2026-09-19T10:00:00Z"
    assert stamped["bundle_id"] == again["bundle_id"]
    assert again["generated_at"] == exported.result.window.as_of.isoformat()


def test_glossary_explains_every_code_the_engine_can_emit(exported) -> None:
    glossary = exported.manifest["glossary"]
    assert set(contracts.PILLAR_GATES) <= set(glossary["gates"])
    assert set(contracts.SCORE_FLAGS) <= set(glossary["flags"])
    assert set(contracts.CAP_KEYS) <= set(glossary["caps"])
    reasons = {*contracts.ABSTAIN_REASONS, *contracts.SUPPRESSION_REASONS, *contracts.TRAJECTORY_REASONS}
    assert reasons <= set(glossary["reasons"])
    used = {"gates": set(), "flags": set(), "caps": set(), "reasons": set()}
    for _, entity in _entity_files(exported.path):
        for entry in entity["months"]:
            used["flags"] |= set(entry["flags"])
            used["caps"] |= set(entry["cap"]["fired"])
            used["gates"] |= {gate for pillar in entry["pillars"] for gate in pillar["gates"]}
            used["gates"] |= set((entry["outlook"] or {}).get("gates", ()))
            used["reasons"] |= {entry["verdict"]["reason"], (entry["abstain"] or {}).get("reason")} - {None}
            assert not (entry["abstain"] and entry["verdict"]["available"]), (entity["id"], entry["month"])
    for section, codes in used.items():
        missing = codes - set(glossary[section])
        assert not missing, (section, missing)
        assert not [code for code in codes if glossary[section][code].startswith("Código del motor")]


def test_company_truth_follows_the_liquidity_inheritance(exported, synthetic) -> None:
    companies = {entity["id"]: entity for kind, entity in _entity_files(exported.path) if kind == "company"}
    for entity in companies.values():
        if entity["inherits_liquidity"]:
            assert entity["truth"].startswith(TRUTH_TEXTS["swept"])
    for _, entity in _entity_files(exported.path):
        assert len(entity["profile"]) in (0, len(contracts.PROFILE_KEYS))
    # archetypes: swept subsidiary, treasury centre, captive company funded by the group
    swept = companies[synthetic.swept_company_id]
    assert swept["inherits_liquidity"] and swept["truth"] == TRUTH_TEXTS["swept"]
    assert "inherited_from_group" in swept["months"][-1]["pillars"][0]["gates"]
    assert companies[synthetic.treasury_company_id]["truth"] == TRUTH_TEXTS["treasury_centre"]
    captive = companies[synthetic.no_external_revenue_company_id]["truth"]
    assert TRUTH_TEXTS["group_funded"] in captive and TRUTH_TEXTS["no_external_revenue"] in captive
    assert any(entity["truth"] is None for entity in companies.values())
    # the group file repeats the head of each company file
    for _, group in ((k, e) for k, e in _entity_files(exported.path) if k == "group"):
        for item in group["companies"]:
            assert item["truth"] == companies[item["id"]]["truth"]
    evidence = [json.loads(p.read_text(encoding="utf-8")) for p in (exported.path / "evidence").glob("*.json")]
    assert len(evidence) == len(_entity_files(exported.path))
    assert any(row["pillar"] is not None for item in evidence for month in item["months"] for row in month["rows"])


def test_receipt_is_minimal_without_validation_and_maps_a_validation_report(exported, tmp_path) -> None:
    minimal = json.loads((exported.path / "receipt.json").read_text(encoding="utf-8"))
    assert minimal["checks"] == []
    zero = [item for item in minimal["signals"] if item["weight"] == 0]
    assert {"industry", "customer_concentration", "seasonality"} <= {item["name"] for item in zero}
    assert all(item["why"] for item in minimal["signals"])

    report = {
        "dataset_hash": exported.result.dataset_hash,
        "params_hash": exported.result.params.sha256,
        "engine_version": contracts.ENGINE_VERSION,
        "isolation": {"pass": True, "n": 6, "max_abs_diff": 0.0, "tol": 1e-9},
        "additivity": {"pass": False, "max_abs_gap": 0.2},
        "injection": {"pass": None, "delay_distribution": {"1": 3, "2": 5}, "false_alert_rate": 0.01},
    }
    path = tmp_path / "validation.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    export_from_result(exported.result, tmp_path / "with-receipt", validation_path=path)
    assert check_bundle(tmp_path / "with-receipt") == []
    checks = {
        item["key"]: item
        for item in json.loads((tmp_path / "with-receipt" / "receipt.json").read_text(encoding="utf-8"))["checks"]
    }
    assert checks["isolation"]["status"] == "pass" and checks["additivity"]["status"] == "fail"
    assert checks["injection"]["status"] == "info" and len(checks["injection"]["bars"]) == 2
    assert checks["determinism"]["status"] == "not_run"

    # a report about another dataset is never shown as this bundle's receipt
    export_bundle(exported.result, tmp_path / "foreign", receipt={**report, "dataset_hash": "other"})
    assert check_bundle(tmp_path / "foreign") == []
    foreign = json.loads((tmp_path / "foreign" / "receipt.json").read_text(encoding="utf-8"))["checks"]
    assert {item["status"] for item in foreign} == {"not_run"}
    # no report on disk: minimal receipt
    export_from_result(exported.result, tmp_path / "none", validation_path=tmp_path / "missing.json")
    assert json.loads((tmp_path / "none" / "receipt.json").read_text(encoding="utf-8"))["checks"] == []
