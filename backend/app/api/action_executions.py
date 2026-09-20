"""Operational tracking. No payment, financing request or email is sent here."""
import json
import math
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..config import settings
from ..database import get_session
from ..models import ActionExecution, ActionExecutionEvent

router = APIRouter(prefix="/api/v1/action-executions", tags=["action-executions"])
METRICS = {"liquidity": "buffer_days", "payments": "ap_days_beyond_terms", "collections": "ar_days_beyond_terms", "activity": "activity_coverage", "debt": "debt_burden"}


class Scope(BaseModel):
    entity_id: str = Field(pattern=r"^(COMP|GROUP)_\d+$")
    group_id: str = Field(pattern=r"^GROUP_\d+$")
    kind: Literal["company", "group"]


class FinancingChoice(BaseModel):
    entity_id: str = Field(pattern=r"^(COMP|GROUP)_\d+$")
    id: str = Field(min_length=1, max_length=200)
    banks: list[str] = Field(default_factory=list, max_length=30)


class Start(Scope):
    corte: str = Field(pattern=r"^\d{4}-\d{2}$")
    bundle_id: str
    action_ids: list[str] = Field(default_factory=list, max_length=20)
    financing: list[FinancingChoice] = Field(default_factory=list, max_length=200)
    actor: Literal["CFO", "Embat"]


class Change(BaseModel):
    group_id: str
    status: Literal["en_curso", "pausada", "completada"]
    version: int = Field(ge=1)
    actor: Literal["CFO", "Embat"]
    note: str = Field(default="", max_length=2000)


def source(scope: Scope):
    root = settings.bundle_dir.resolve()
    path = root / ("companies" if scope.kind == "company" else "groups") / f"{scope.entity_id}.json"
    try:
        doc = json.loads(path.read_text())
        manifest = json.loads((root / "manifest.json").read_text())
    except (OSError, ValueError):
        raise HTTPException(503, "No se pueden consultar los datos del motor.")
    group = doc.get("group_id") if scope.kind == "company" else doc.get("id")
    if group != scope.group_id or doc.get("id") != scope.entity_id:
        raise HTTPException(404, "La entidad no pertenece a este grupo.")
    return doc, manifest["bundle_id"]


def measurement(doc, index, metric, unit):
    series = next((s for s in doc.get("series", []) if s["key"] == metric), None)
    if not series:
        return None
    offset = index + len(series["values"]) - len(doc["months"])
    value = series["values"][offset] if 0 <= offset < len(series["values"]) else None
    if value is None or not isinstance(value, (float, int)) or not math.isfinite(value):
        return None
    return value * 100 if unit == "%" and series["unit"] == "ratio" else value


def rows(session, entity_id, group_id):
    return session.exec(select(ActionExecution).where(ActionExecution.entity_id == entity_id, ActionExecution.group_id == group_id).order_by(ActionExecution.created_at.desc(), ActionExecution.id)).all()


def payload(session, row):
    events = session.exec(select(ActionExecutionEvent).where(ActionExecutionEvent.execution_id == row.id).order_by(ActionExecutionEvent.created_at, ActionExecutionEvent.id)).all()
    return {**row.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events]}


@router.get("")
def listing(entity_id: str, group_id: str, session: Session = Depends(get_session)):
    return [payload(session, row) for row in rows(session, entity_id, group_id)]


@router.post("")
def start(body: Start, session: Session = Depends(get_session)):
    doc, bundle = source(body)
    if bundle != body.bundle_id or not doc["months"] or doc["months"][-1]["month"] != body.corte:
        raise HTTPException(409, "Ejecuta las acciones desde el último cierre disponible. Actualiza la página.")
    month = doc["months"][-1]
    actions = {a["id"]: a for a in month.get("actions", [])}
    if any(key not in actions for key in body.action_ids):
        raise HTTPException(422, "Alguna acción ya no está disponible. Actualiza la página.")
    if not body.action_ids and not body.financing:
        raise HTTPException(422, "Elige al menos una acción o una gestión de financiación.")
    selected = list(dict.fromkeys(body.action_ids))
    for choice in body.financing:
        related, _ = source(Scope(entity_id=choice.entity_id, group_id=body.group_id, kind="group" if choice.entity_id.startswith("GROUP_") else "company"))
        if body.kind == "company" and choice.entity_id != body.entity_id:
            raise HTTPException(422, "La financiación debe pertenecer a esta empresa.")
        closing = next((m for m in related["months"] if m["month"] == body.corte), {})
        instrument = next((f for f in closing.get("financing", []) if f["id"] == choice.id), None)
        if not instrument or any(not bank.strip() or len(bank) > 200 for bank in choice.banks):
            raise HTTPException(422, "Revisa la financiación o los bancos elegidos.")
        key = f"financing:{choice.entity_id}:{choice.id}"
        actions[key] = {**instrument, "id": key, "pillar": "financing", "financing": True, "source_entity_id": choice.entity_id, "banks": list(dict.fromkeys(choice.banks)), "target": None, "unit": ""}
        if key not in selected:
            selected.append(key)
    try:
        for key in selected:
            # A refreshed bundle must not duplicate a decision for the same monthly action.
            identity = str(uuid5(NAMESPACE_URL, f"rumbo:{body.entity_id}:{body.corte}:{key}"))
            if session.get(ActionExecution, identity):
                continue
            action = actions[key]
            metric = METRICS.get(action["pillar"])
            baseline = measurement(doc, len(doc["months"]) - 1, metric, action.get("unit"))
            snapshot = {**action, "metric": metric, "baseline": baseline, "corte": body.corte, "bundle_id": bundle, "score_tenths": month.get("shown")}
            row = ActionExecution(id=identity, entity_id=body.entity_id, group_id=body.group_id, kind=body.kind, snapshot=snapshot)
            session.add(row)
            session.flush()
            session.add(ActionExecutionEvent(id=str(uuid4()), execution_id=identity, actor=body.actor, kind="decision", payload={"status": "en_curso", "note": "Puesta en marcha", "version": 1}))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Las acciones se están guardando en otra sesión. Actualiza el seguimiento.")
    return [payload(session, row) for row in rows(session, body.entity_id, body.group_id)]


@router.post("/refresh")
def refresh(body: Scope, session: Session = Depends(get_session)):
    doc, bundle = source(body)
    executions = rows(session, body.entity_id, body.group_id)
    try:
        for row in executions:
            snap = row.snapshot
            for index, month in enumerate(doc["months"]):
                if month["month"] <= snap["corte"]:
                    continue
                identity = str(uuid5(NAMESPACE_URL, f"{row.id}:{bundle}:{month['month']}"))
                if session.get(ActionExecutionEvent, identity):
                    continue
                value = measurement(doc, index, snap["metric"], snap.get("unit"))
                session.add(ActionExecutionEvent(id=identity, execution_id=row.id, actor="Motor", kind="measurement", payload={"month": month["month"], "value": value, "score_tenths": month.get("shown"), "bundle_id": bundle}))
        session.commit()
    except IntegrityError:
        session.rollback()  # Another reader has already captured this source revision.
    return [payload(session, row) for row in rows(session, body.entity_id, body.group_id)]


@router.patch("/{execution_id}")
def change(execution_id: str, body: Change, session: Session = Depends(get_session)):
    row = session.get(ActionExecution, execution_id)
    if not row or row.group_id != body.group_id:
        raise HTTPException(404, "Acción no encontrada.")
    previous_status = row.status
    result = session.execute(update(ActionExecution).where(ActionExecution.id == execution_id, ActionExecution.version == body.version).values(status=body.status, version=body.version + 1))
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Otra persona actualizó esta acción. Actualiza antes de guardar.")
    session.add(ActionExecutionEvent(id=str(uuid4()), execution_id=row.id, actor=body.actor, kind="decision", payload={"status": body.status, "previous_status": previous_status, "note": body.note.strip(), "version": body.version + 1}))
    session.commit()
    session.refresh(row)
    return payload(session, row)
