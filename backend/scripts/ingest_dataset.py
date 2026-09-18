from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from sqlalchemy import create_engine
from sqlmodel import Session, select

from xray_engine.scoring import FEATURE_VERSION, MODEL_VERSION

from app.models import (
    AlertRecord,
    Entity,
    ScoreDriverRecord,
    ScoreRun,
    ScoreSnapshotRecord,
    Workspace,
)

RAW_DIR = Path("/data/raw")
SCORES_PATH = Path("/app/artifacts/scores.parquet")
WORKSPACE_ID = "WORKSPACE_DEMO"


def add_entities(session: Session, scores: pl.DataFrame) -> int:
    companies = session.exec(select(Entity.id, Entity.kind)) if False else None
    existing = {row.id for row in session.exec(select(Entity))}
    added = 0
    companies = pl.read_csv(RAW_DIR / "companies.csv")
    for gid in sorted(set(companies["group_id"].to_list())):
        if gid not in existing:
            session.add(Entity(id=gid, workspace_id=WORKSPACE_ID, name=gid, kind="group"))
            added += 1
    for row in companies.iter_rows(named=True):
        cid = row["company_id"]
        if cid in existing:
            continue
        session.add(
            Entity(
                id=cid,
                workspace_id=WORKSPACE_ID,
                parent_id=row["group_id"],
                name=cid,
                kind="company",
            )
        )
        added += 1
    return added


def ingest_scores(session: Session, scores: pl.DataFrame) -> tuple[str, int, int]:
    dataset_hash = scores["dataset_hash"][0]
    run_id = f"RUN_{dataset_hash}"
    alerts_existing = {row.entity_id for row in session.exec(select(AlertRecord))}
    if session.get(ScoreRun, run_id) is None:
        session.add(
            ScoreRun(
                id=run_id,
                dataset_hash=dataset_hash,
                feature_version=FEATURE_VERSION,
                model_version=MODEL_VERSION,
                status="completed",
                completed_at=datetime.now(UTC),
            )
        )
    snapshots_processed = 0
    latest = scores.sort("month").group_by("company_id").last()
    for row in latest.iter_rows(named=True):
        entity_id = row["company_id"]
        snapshot_id = f"SNAP_{entity_id}_{row['month']}"
        if session.get(ScoreSnapshotRecord, snapshot_id) is None:
            session.add(
                ScoreSnapshotRecord(
                    id=snapshot_id,
                    run_id=run_id,
                    entity_id=entity_id,
                    month=row["month"],
                    score=row["score"],
                    delta=row["delta"],
                    trend=row["trend"],
                    persistence_months=row["persistence_months"],
                    confidence=row["confidence"],
                    detected_since=row["detected_since"] if row["detected_since"] else None,
                )
            )
        for driver in row["drivers"]:
            driver_id = f"DRV_{snapshot_id}_{driver['feature']}"
            if session.get(ScoreDriverRecord, driver_id) is None:
                session.add(
                    ScoreDriverRecord(
                        id=driver_id,
                        snapshot_id=snapshot_id,
                        feature=driver["feature"],
                        direction=driver["direction"],
                        contribution=driver["contribution"],
                        observed=driver["observed"],
                        baseline=driver["baseline"],
                        evidence=driver["evidence"],
                    )
                )
        if (
            entity_id not in alerts_existing
            and row["trend"] == "deteriorating"
            and row["persistence_months"] >= 3
        ):
            severity = "high" if row["score"] < 45 else "medium"
            session.add(
                AlertRecord(
                    id=f"ALERT_{entity_id}",
                    entity_id=entity_id,
                    snapshot_id=snapshot_id,
                    kind="persistent_deterioration",
                    severity=severity,
                    status="new",
                )
            )
        snapshots_processed += 1
    return run_id, snapshots_processed


def main() -> None:
    from app.config import settings

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    scores = pl.read_parquet(SCORES_PATH)
    with Session(engine) as session:
        if session.get(Workspace, WORKSPACE_ID) is None:
            session.add(Workspace(id=WORKSPACE_ID, name="Embat X-Ray"))
            session.commit()
        entities_added = add_entities(session, scores)
        run_id, snapshots_processed = ingest_scores(session, scores)
        session.commit()
    print(
        f"entities added: {entities_added} · run: {run_id} · snapshots processed: {snapshots_processed}"
    )


if __name__ == "__main__":
    main()
