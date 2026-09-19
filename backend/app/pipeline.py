from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, create_engine
from xray_engine.export import export_from_result
from xray_engine.scoring import score_dataset, write_outputs

from .industry import run_classification
from .ingest import ingest_dataset
from .publish import publish_outputs


@dataclass(frozen=True)
class SyncResult:
    dataset_hash: str
    ingest_skipped: bool
    classification_skipped: bool
    source_counts: dict[str, int]
    published_counts: dict[str, int]
    bundle_id: str


def _classify(input_dir: Path, database_url: str) -> tuple[dict[str, int], bool]:
    db_engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(db_engine) as session:
            _, counts, skipped = run_classification(session, input_dir)
    finally:
        db_engine.dispose()
    return counts, skipped


def sync_dataset(
    *,
    input_dir: Path,
    out_dir: Path,
    bundle_dir: Path,
    database_url: str,
    evidence_months: int = 24,
) -> SyncResult:
    dataset_hash, source_counts, ingest_skipped = ingest_dataset(
        input_dir, database_url
    )
    _, classification_skipped = _classify(input_dir, database_url)

    scored = score_dataset(input_dir)
    if scored.dataset_hash != dataset_hash:
        raise RuntimeError(
            f"Dataset changed during synchronization: ingested {dataset_hash}, scored {scored.dataset_hash}"
        )

    write_outputs(scored, out_dir)
    validation_path = out_dir / "validation.json"
    manifest = export_from_result(
        scored,
        bundle_dir,
        validation_path=validation_path if validation_path.is_file() else None,
        evidence_months=evidence_months,
    )
    published_hash, published_counts = publish_outputs(out_dir, database_url)
    if published_hash != dataset_hash:
        raise RuntimeError(
            f"Published dataset {published_hash} does not match ingested dataset {dataset_hash}"
        )

    return SyncResult(
        dataset_hash=dataset_hash,
        ingest_skipped=ingest_skipped,
        classification_skipped=classification_skipped,
        source_counts=source_counts,
        published_counts=published_counts,
        bundle_id=str(manifest["bundle_id"]),
    )
