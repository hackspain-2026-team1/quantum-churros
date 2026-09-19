"""xray-score: predict on any folder, frozen params or nothing."""

from __future__ import annotations

import csv
import json

import polars as pl
import pytest
from typer.testing import CliRunner
from xray_engine.cli import app
from xray_engine.contracts import PILLAR_KEYS, SNAPSHOT_SCHEMA
from xray_engine.params import DEFAULT_PARAMS_PATH, load_params

runner = CliRunner()
REQUIRED = ["entity_id", "month", "score", "band", "direction", "nature", "confidence", "abstained"]


@pytest.fixture(scope="module")
def predicted(synthetic, tmp_path_factory):
    root = tmp_path_factory.mktemp("cli")
    done = runner.invoke(app, [
        "predict", str(synthetic.path), "--out", str(root / "artifacts" / "run"),
        "--cache-dir", str(root / "cache"),
    ])
    assert done.exit_code == 0, done.output
    return root / "artifacts" / "run", done.output


def test_predict_writes_both_kinds_and_every_month(predicted, synthetic, params) -> None:
    out, output = predicted
    scores = pl.read_parquet(out / "scores.parquet")
    assert dict(scores.schema) == SNAPSHOT_SCHEMA
    assert set(scores["entity_kind"]) == {"group", "company"}
    assert scores["month"].min() == synthetic.first_month and scores["month"].max() == synthetic.last_month
    assert set(scores["params_hash"]) == {params.sha256}
    assert params.sha256[:12] in output
    assert scores.select("entity_kind", "entity_id", "month").is_unique().all()
    assert {"alerts.parquet", "panel.parquet"} <= {path.name for path in out.iterdir()}


@pytest.mark.parametrize("kind", ["group", "company"])
def test_csv_views_lead_with_the_answer(predicted, kind) -> None:
    out, _ = predicted
    name = "scores_groups.csv" if kind == "group" else "scores_companies.csv"
    with (out / name).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    header = list(rows[0])
    assert header[: len(REQUIRED)] == REQUIRED
    assert header[len(REQUIRED): len(REQUIRED) + len(PILLAR_KEYS)] == [f"pillars_{key}" for key in PILLAR_KEYS]
    assert {"horizon", "drift_points", "size_band", "params_hash", "penalty", "cap_adjustment"} <= set(header)
    scores = pl.read_parquet(out / "scores.parquet").filter(pl.col("entity_kind") == kind)
    assert len(rows) == scores.height and {row["entity_kind"] for row in rows} == {kind}
    assert {row["band"] for row in rows} <= {"critical", "watch", "stable", "solid"}
    assert {row["direction"] for row in rows} <= {"stable", "improving", "deteriorating", "perimeter_shift"}
    assert all(0.0 <= float(row["score"]) <= 100.0 for row in rows)


def test_predict_exports_the_bundle_with_the_asked_months_of_evidence(synthetic, tmp_path) -> None:
    sizes = {}
    for months in (2, 24):
        bundle = tmp_path / f"bundle{months}"
        done = runner.invoke(app, [
            "predict", str(synthetic.path), "--out", str(tmp_path / "run"), "--export-dir", str(bundle),
            "--evidence-months", str(months), "--cache-dir", str(tmp_path / "cache"),
        ])
        assert done.exit_code == 0, done.output
        assert "Wrote bundle" in done.output and (bundle / "receipt.json").is_file()
        files = sorted((bundle / "evidence").glob("*.json"))
        assert files
        kept = [len(json.loads(path.read_text(encoding="utf-8"))["months"]) for path in files]
        assert max(kept) == min(months, max(kept)) and max(kept) <= months
        sizes[months] = sum(path.stat().st_size for path in files)
    assert sizes[2] < sizes[24]
    # groups and companies keep every month whatever the evidence depth
    group = synthetic.group_ids[0]
    short, full = (json.loads((tmp_path / f"bundle{months}" / "groups" / f"{group}.json").read_text(encoding="utf-8"))
                   for months in (2, 24))
    assert short == full


def test_a_tampered_params_file_is_refused(synthetic, tmp_path) -> None:
    data = json.loads(DEFAULT_PARAMS_PATH.read_text(encoding="utf-8"))
    data["penalty"]["lam"] = 0.4  # content no longer matches the stamped sha256
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    for command in (["predict", str(synthetic.path), "--out", str(tmp_path / "out")],
                    ["export", str(synthetic.path), "--export-dir", str(tmp_path / "bundle")]):
        done = runner.invoke(app, [*command, "--params", str(tampered), "--cache-dir", str(tmp_path / "cache")])
        assert done.exit_code == 2
        assert "sha256" in done.output
    assert not (tmp_path / "out").exists() and not (tmp_path / "bundle").exists()


def test_fit_reference_then_predict_with_the_new_file(synthetic, tmp_path) -> None:
    fitted, report = tmp_path / "fitted.json", tmp_path / "report.json"
    done = runner.invoke(app, [
        "fit-reference", str(synthetic.path), "--out", str(fitted), "--report", str(report),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert done.exit_code == 0, done.output
    params = load_params(fitted)
    assert params.fitted and params.sha256 in done.output and "reference medians" in done.output
    assert DEFAULT_PARAMS_PATH.resolve() != fitted.resolve()
    assert load_params().sha256 == load_params(DEFAULT_PARAMS_PATH).sha256  # the frozen file is untouched

    done = runner.invoke(app, [
        "predict", str(synthetic.path), "--out", str(tmp_path / "out"), "--params", str(fitted),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert done.exit_code == 0, done.output
    assert set(pl.read_parquet(tmp_path / "out" / "scores.parquet")["params_hash"]) == {params.sha256}


def test_validation_report_is_embedded_in_a_bundle_with_matching_params(synthetic, tmp_path) -> None:
    artifacts = tmp_path / "artifacts"
    validation = runner.invoke(app, [
        "validate", str(synthetic.path), "--out", str(artifacts / "validation.json"), "--quick",
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert validation.exit_code == 0, validation.output

    exported = runner.invoke(app, [
        "predict", str(synthetic.path), "--out", str(artifacts),
        "--export-dir", str(tmp_path / "bundle"), "--cache-dir", str(tmp_path / "cache"),
    ])
    assert exported.exit_code == 0, exported.output
    report = json.loads((artifacts / "validation.json").read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "bundle" / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["params_hash"] == report["params_hash"]
    assert receipt["dataset_hash"] == report["dataset_hash"]
    assert {item["key"]: item["status"] for item in receipt["checks"]} == {
        item["key"]: item["status"] for item in report["checks"]
    }


def test_export_command_writes_the_bundle(synthetic, tmp_path) -> None:
    done = runner.invoke(app, [
        "export", str(synthetic.path), "--export-dir", str(tmp_path / "bundle"),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert done.exit_code == 0, done.output
    manifest = json.loads((tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["params_hash"] == load_params().sha256
