from pathlib import Path
from types import SimpleNamespace

import pytest
from app import pipeline


def test_sync_dataset_runs_the_existing_stages_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_hash = "d" * 64
    events: list[str] = []

    def ingest(input_dir: Path, database_url: str):
        events.append("ingest")
        return dataset_hash, {"groups": 250}, True

    def classify(input_dir: Path, database_url: str):
        events.append("classify")
        return {"services": 100}, True

    def score(input_dir: Path):
        events.append("score")
        return SimpleNamespace(dataset_hash=dataset_hash)

    def write(scored: object, out_dir: Path):
        events.append("write")

    def export(scored: object, bundle_dir: Path, **kwargs: object):
        events.append("export")
        return {"bundle_id": "bundle-123"}

    def publish(out_dir: Path, database_url: str):
        events.append("publish")
        return dataset_hash, {"entity_month_score": 1000}

    monkeypatch.setattr(pipeline, "ingest_dataset", ingest)
    monkeypatch.setattr(pipeline, "_classify", classify)
    monkeypatch.setattr(pipeline, "score_dataset", score)
    monkeypatch.setattr(pipeline, "write_outputs", write)
    monkeypatch.setattr(pipeline, "export_from_result", export)
    monkeypatch.setattr(pipeline, "publish_outputs", publish)

    result = pipeline.sync_dataset(
        input_dir=tmp_path / "raw",
        out_dir=tmp_path / "artifacts",
        bundle_dir=tmp_path / "bundle",
        database_url="postgresql://example/xray",
    )

    assert events == ["ingest", "classify", "score", "write", "export", "publish"]
    assert result.dataset_hash == dataset_hash
    assert result.ingest_skipped is True
    assert result.classification_skipped is True
    assert result.bundle_id == "bundle-123"


def test_sync_dataset_refuses_a_source_that_changes_while_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipeline,
        "ingest_dataset",
        lambda input_dir, database_url: ("a" * 64, {}, False),
    )
    monkeypatch.setattr(pipeline, "_classify", lambda input_dir, database_url: ({}, False))
    monkeypatch.setattr(
        pipeline,
        "score_dataset",
        lambda input_dir: SimpleNamespace(dataset_hash="b" * 64),
    )

    with pytest.raises(RuntimeError, match="Dataset changed during synchronization"):
        pipeline.sync_dataset(
            input_dir=tmp_path / "raw",
            out_dir=tmp_path / "artifacts",
            bundle_dir=tmp_path / "bundle",
            database_url="postgresql://example/xray",
        )
