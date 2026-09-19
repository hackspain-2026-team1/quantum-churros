"""Explicit, idempotent demo decisions using real historical engine snapshots.

Run only when requested: python -m app.seed_action_demo --entity-id COMP_... --group-id GROUP_...
Never runs at startup or during migrations. Demo decisions are visibly marked.
"""
import argparse
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlmodel import Session
from .api.action_executions import METRICS, Scope, measurement, refresh, source
from .database import engine
from .models import ActionExecution, ActionExecutionEvent


def seed(entity_id: str, group_id: str):
    scope = Scope(entity_id=entity_id, group_id=group_id, kind="company")
    doc, bundle = source(scope)
    candidates = []
    for i, month in enumerate(doc["months"][:-1]):
        for action in month.get("actions", []):
            metric = METRICS.get(action["pillar"])
            initial = measurement(doc, i, metric, action.get("unit"))
            latest = measurement(doc, len(doc["months"]) - 1, metric, action.get("unit"))
            target = action.get("target")
            if initial is None or latest is None or target is None or target == initial:
                continue
            candidates.append((month, action, initial, (latest - initial) / (target - initial)))
    used = set()
    with Session(engine) as session:
        for state in ["en_curso", "pausada", "completada"]:
            suitable = [v for v in candidates if (v[0]["month"], v[1]["id"]) not in used and (v[3] >= 1 if state == "completada" else v[3] < 1)]
            if not suitable:
                continue
            month, action, baseline, _ = suitable[-1]
            used.add((month["month"], action["id"]))
            identity = str(uuid5(NAMESPACE_URL, f"rumbo-demo:{entity_id}:{state}"))
            if session.get(ActionExecution, identity):
                continue
            created = datetime.fromisoformat(month["month"] + "-28T10:00:00").replace(tzinfo=UTC)
            snapshot = {**action, "demo": True, "metric": METRICS[action["pillar"]], "baseline": baseline, "corte": month["month"], "bundle_id": bundle, "score_tenths": month.get("shown")}
            row = ActionExecution(id=identity, entity_id=entity_id, group_id=group_id, kind="company", status=state, version=1 if state == "en_curso" else 2, snapshot=snapshot, created_at=created)
            session.add(row)
            session.flush()
            session.add(ActionExecutionEvent(id=str(uuid5(NAMESPACE_URL, identity + ":start")), execution_id=identity, actor="Demo", kind="decision", created_at=created, payload={"status": "en_curso", "note": "Ejemplo de decisión anterior para la demo. Objetivo e indicadores tomados del motor; no representa una gestión real.", "version": 1}))
            if state != "en_curso":
                session.add(ActionExecutionEvent(id=str(uuid5(NAMESPACE_URL, identity + ":state")), execution_id=identity, actor="Demo", kind="decision", created_at=created + timedelta(days=1), payload={"status": state, "note": "Estado de demostración: gestión pausada para revisión." if state == "pausada" else "Estado de demostración: tarea completada. La barra muestra el resultado observado, no una atribución causal.", "version": 2}))
        session.commit()
        records = refresh(scope, session)
        return [{"id": r["id"], "status": r["status"], "corte": r["snapshot"]["corte"]} for r in records if r["snapshot"].get("demo")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--group-id", required=True)
    args = parser.parse_args()
    print(seed(args.entity_id, args.group_id))
