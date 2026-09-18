from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select
from xray_engine.industry_classifier import (
    CLASSIFIER_VERSION,
    IndustryClassification,
    classify_dataset,
    distribution,
    signals_to_json,
)

from .models import EntityIndustry, IndustryClassificationRead


def classification_exists(
    session: Session, dataset_hash: str, classifier_version: str = CLASSIFIER_VERSION
) -> bool:
    record = session.exec(
        select(EntityIndustry)
        .where(EntityIndustry.dataset_hash == dataset_hash)
        .where(EntityIndustry.classifier_version == classifier_version)
        .limit(1)
    ).first()
    return record is not None


def persist_classifications(
    session: Session, dataset_hash: str, classifications: list[IndustryClassification]
) -> int:
    for item in classifications:
        record_id = f"{dataset_hash}_{item.entity_id}_{item.classifier_version}"
        session.merge(
            EntityIndustry(
                id=record_id,
                dataset_hash=dataset_hash,
                entity_id=item.entity_id,
                industry_slug=item.industry_slug,
                industry_label=item.industry_label,
                confidence=item.confidence,
                source=item.source,
                reason=item.reason,
                classifier_version=item.classifier_version,
                signals_json=signals_to_json(item.signals),
                classified_at=datetime.now(UTC),
            )
        )
    session.commit()
    return len(classifications)


def run_classification(
    session: Session,
    input_dir: Path,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[str, dict[str, int], bool]:
    dataset_hash, classifications = classify_dataset(input_dir)
    if not force and classification_exists(session, dataset_hash):
        return dataset_hash, {}, True
    counts = distribution(classifications)
    if dry_run:
        return dataset_hash, counts, False
    persist_classifications(session, dataset_hash, classifications)
    return dataset_hash, counts, False


def latest_dataset_hash(session: Session) -> str | None:
    record = session.exec(
        select(EntityIndustry.dataset_hash)
        .order_by(EntityIndustry.classified_at.desc())
        .limit(1)
    ).first()
    return record


def _to_read(record: EntityIndustry) -> IndustryClassificationRead:
    return IndustryClassificationRead(
        entity_id=record.entity_id,
        industry_slug=record.industry_slug,
        industry_label=record.industry_label,
        confidence=record.confidence,
        source=record.source,
        reason=record.reason,
        classifier_version=record.classifier_version,
        dataset_hash=record.dataset_hash,
    )


def get_classification(
    session: Session,
    entity_id: str,
    dataset_hash: str | None = None,
    classifier_version: str = CLASSIFIER_VERSION,
) -> IndustryClassificationRead | None:
    active_hash = dataset_hash or latest_dataset_hash(session)
    if active_hash is None:
        return None
    record = session.exec(
        select(EntityIndustry)
        .where(EntityIndustry.dataset_hash == active_hash)
        .where(EntityIndustry.entity_id == entity_id.upper())
        .where(EntityIndustry.classifier_version == classifier_version)
    ).first()
    return _to_read(record) if record else None


def get_classifications(
    session: Session,
    entity_ids: list[str],
    dataset_hash: str | None = None,
    classifier_version: str = CLASSIFIER_VERSION,
) -> dict[str, IndustryClassificationRead]:
    if not entity_ids:
        return {}
    active_hash = dataset_hash or latest_dataset_hash(session)
    if active_hash is None:
        return {}
    normalized = [entity_id.upper() for entity_id in entity_ids]
    records = session.exec(
        select(EntityIndustry)
        .where(EntityIndustry.dataset_hash == active_hash)
        .where(EntityIndustry.entity_id.in_(normalized))
        .where(EntityIndustry.classifier_version == classifier_version)
    ).all()
    return {record.entity_id: _to_read(record) for record in records}


def industry_distribution(
    session: Session,
    dataset_hash: str | None = None,
    classifier_version: str = CLASSIFIER_VERSION,
) -> dict[str, int]:
    active_hash = dataset_hash or latest_dataset_hash(session)
    if active_hash is None:
        return {}
    records = session.exec(
        select(EntityIndustry)
        .where(EntityIndustry.dataset_hash == active_hash)
        .where(EntityIndustry.classifier_version == classifier_version)
    ).all()
    counts: dict[str, int] = {}
    for record in records:
        counts[record.industry_slug] = counts.get(record.industry_slug, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))
