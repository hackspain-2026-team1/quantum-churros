import base64
import json
import zlib
from pathlib import Path

import polars as pl

ROOT = Path("/app")
scores = pl.read_parquet(ROOT / "artifacts/scores.parquet")
companies = pl.read_csv(Path("/data/raw/companies.csv"))

latest = scores.sort("month").group_by("company_id").last()
dataset_hash = scores["dataset_hash"][0]
run_id = f"RUN_{dataset_hash}"

entities = []
seen = set()
for row in companies.iter_rows(named=True):
    gid = row["group_id"]
    if gid not in seen:
        seen.add(gid)
        entities.append({"id": gid, "name": gid, "kind": "group", "parent_id": None, "workspace_id": "WORKSPACE_DEMO"})
    seen.add(row["company_id"])
    entities.append(
        {
            "id": row["company_id"],
            "name": row["company_id"],
            "kind": "company",
            "parent_id": row["group_id"],
            "workspace_id": "WORKSPACE_DEMO",
        }
    )

snapshots = []
drivers = []
alerts = []
for row in latest.iter_rows(named=True):
    entity_id = row["company_id"]
    month = row["month"]
    snapshot_id = f"SNAP_{entity_id}_{month}"
    detected = row["detected_since"]
    snapshots.append(
        {
            "id": snapshot_id,
            "run_id": run_id,
            "entity_id": entity_id,
            "month": str(month),
            "score": row["score"],
            "delta": row["delta"],
            "trend": row["trend"],
            "persistence_months": row["persistence_months"],
            "confidence": row["confidence"],
            "detected_since": str(detected) if detected else None,
        }
    )
    for d in row["drivers"]:
        drivers.append(
            {
                "id": f"DRV_{snapshot_id}_{d['feature']}",
                "snapshot_id": snapshot_id,
                "feature": d["feature"],
                "direction": d["direction"],
                "contribution": d["contribution"],
                "observed": d["observed"],
                "baseline": d["baseline"],
                "evidence": d["evidence"],
            }
        )
    if row["trend"] == "deteriorating" and row["persistence_months"] >= 3:
        alerts.append(
            {
                "id": f"ALERT_{entity_id}",
                "entity_id": entity_id,
                "snapshot_id": snapshot_id,
                "kind": "persistent_deterioration",
                "severity": "high" if row["score"] < 45 else "medium",
                "status": "new",
            }
        )

payload = {
    "run": {
        "id": run_id,
        "dataset_hash": dataset_hash,
        "feature_version": scores["feature_version"][0],
        "model_version": scores["model_version"][0],
    },
    "entities": entities,
    "snapshots": snapshots,
    "drivers": drivers,
    "alerts": alerts,
}
blob = base64.b64encode(zlib.compress(json.dumps(payload).encode())).decode()

revision = Path("/app/backend/migrations/versions/20260918_02_seed_baseline_dataset.py")
revision.write_text(
    '"""Seed operational X-Ray data from the baseline dataset run.\n\n'
    "Revision ID: 20260918_02\n"
    "Revises: 20260918_01\n"
    '"""\n\n'
    'revision = "20260918_02"\n'
    'down_revision = "20260918_01"\n'
    "branch_labels = None\n"
    "depends_on = None\n\n"
    "import base64\n"
    "import json\n"
    "import zlib\n\n"
    "from sqlalchemy import insert, select\n\n"
    "from alembic import op\n\n"
    "from app.models import (\n"
    "    AlertRecord,\n"
    "    Entity,\n"
    "    ScoreDriverRecord,\n"
    "    ScoreRun,\n"
    "    ScoreSnapshotRecord,\n"
    ")\n\n"
    f'PAYLOAD = "{blob}"\n\n\n'
    "def upgrade() -> None:\n"
    "    payload = json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))\n"
    "    conn = op.get_bind()\n"
    "    if conn.execute(select(ScoreRun).where(ScoreRun.id == payload['run']['id'])).first():\n"
    "        return\n"
    "    conn.execute(insert(ScoreRun).values(payload['run']))\n\n"
    "    entity_ids = set(conn.execute(select(Entity.id)).scalars())\n"
    "    fresh = [row for row in payload['entities'] if row['id'] not in entity_ids]\n"
    "    if fresh:\n"
    "        conn.execute(insert(Entity).values(fresh))\n\n"
    "    snapshot_ids = set(conn.execute(select(ScoreSnapshotRecord.id)).scalars())\n"
    "    fresh = [row for row in payload['snapshots'] if row['id'] not in snapshot_ids]\n"
    "    if fresh:\n"
    "        conn.execute(insert(ScoreSnapshotRecord).values(fresh))\n\n"
    "    driver_ids = set(conn.execute(select(ScoreDriverRecord.id)).scalars())\n"
    "    fresh = [row for row in payload['drivers'] if row['id'] not in driver_ids]\n"
    "    if fresh:\n"
    "        conn.execute(insert(ScoreDriverRecord).values(fresh))\n\n"
    "    alert_ids = set(conn.execute(select(AlertRecord.id)).scalars())\n"
    "    fresh = [row for row in payload['alerts'] if row['id'] not in alert_ids]\n"
    "    if fresh:\n"
    "        conn.execute(insert(AlertRecord).values(fresh))\n\n\n"
    "def downgrade() -> None:\n"
    "    payload = json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))\n"
    "    conn = op.get_bind()\n"
    "    conn.execute(AlertRecord.__table__.delete().where(AlertRecord.id.in_([row['id'] for row in payload['alerts']])))\n"
    "    conn.execute(ScoreDriverRecord.__table__.delete().where(ScoreDriverRecord.id.in_([row['id'] for row in payload['drivers']])))\n"
    "    conn.execute(ScoreSnapshotRecord.__table__.delete().where(ScoreSnapshotRecord.id.in_([row['id'] for row in payload['snapshots']])))\n"
    "    conn.execute(Entity.__table__.delete().where(Entity.id.in_([row['id'] for row in payload['entities']])))\n"
    "    conn.execute(ScoreRun.__table__.delete().where(ScoreRun.id == payload['run']['id']))\n"
)
print(f"entities={len(entities)} snapshots={len(snapshots)} drivers={len(drivers)} alerts={len(alerts)} bytes={revision.stat().st_size}")
