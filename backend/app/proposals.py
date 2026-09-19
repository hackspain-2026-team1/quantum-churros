"""Persist client proposals and their follow-up history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from .models import Proposal, ProposalAction, ProposalFinancing


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def to_payload(session: Session, row: Proposal) -> dict[str, Any]:
    acciones = session.exec(
        select(ProposalAction).where(ProposalAction.proposal_id == row.id)
    ).all()
    financiacion = session.exec(
        select(ProposalFinancing).where(ProposalFinancing.proposal_id == row.id)
    ).all()
    return {
        "id": row.id,
        "fecha": _iso(row.created_at),
        "kind": row.kind,
        "entidad": row.entity_id,
        "grupoId": row.group_id,
        "corte": row.corte,
        "bundle_id": row.bundle_id,
        "score_actual_tenths": row.score_actual_tenths,
        "acciones": [
            {
                "id": a.action_id,
                "pillar": a.pillar,
                "title": a.title,
                "uplift_tenths": a.uplift_tenths,
                "new_score_tenths": a.new_score_tenths,
                "current": a.current,
                "target": a.target,
                "unit": a.unit,
            }
            for a in acciones
        ],
        "financiacion": [
            {
                "id": f.instrument_id,
                "kind": f.kind,
                "title": f.title,
                "amount": f.amount,
                "uplift_tenths": f.uplift_tenths,
                "bank": f.bank,
                "rate": f.rate,
                "rate_type": f.rate_type,
                "rate_fuente": f.rate_fuente,
            }
            for f in financiacion
        ],
    }


def list_proposals(session: Session, entity_id: str | None = None) -> list[dict[str, Any]]:
    query = select(Proposal)
    if entity_id:
        query = query.where(Proposal.entity_id == entity_id)
    rows = session.exec(query.order_by(Proposal.created_at.desc())).all()
    return [to_payload(session, row) for row in rows]


def get_proposal(session: Session, proposal_id: str) -> dict[str, Any] | None:
    row = session.get(Proposal, proposal_id)
    if row is None:
        return None
    return to_payload(session, row)


def upsert_proposal(session: Session, body: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(body["id"])
    existing = session.get(Proposal, proposal_id)
    created_at = datetime.now(UTC)
    if existing is not None:
        created_at = existing.created_at
        for child in session.exec(
            select(ProposalAction).where(ProposalAction.proposal_id == proposal_id)
        ).all():
            session.delete(child)
        for child in session.exec(
            select(ProposalFinancing).where(ProposalFinancing.proposal_id == proposal_id)
        ).all():
            session.delete(child)
        session.delete(existing)
        session.flush()

    session.add(
        Proposal(
            id=proposal_id,
            entity_id=str(body["entidad"]),
            group_id=str(body["grupoId"]),
            kind=str(body["kind"]),
            corte=str(body["corte"]),
            bundle_id=str(body["bundle_id"]),
            score_actual_tenths=int(body["score_actual_tenths"]),
            created_at=created_at,
        )
    )
    for i, accion in enumerate(body.get("acciones") or []):
        session.add(
            ProposalAction(
                id=f"{proposal_id}-a{i}",
                proposal_id=proposal_id,
                action_id=str(accion["id"]),
                pillar=str(accion["pillar"]),
                title=str(accion["title"]),
                uplift_tenths=int(accion["uplift_tenths"]),
                new_score_tenths=int(accion["new_score_tenths"]),
                current=accion.get("current"),
                target=accion.get("target"),
                unit=accion.get("unit"),
            )
        )
    for i, item in enumerate(body.get("financiacion") or []):
        session.add(
            ProposalFinancing(
                id=f"{proposal_id}-f{i}",
                proposal_id=proposal_id,
                instrument_id=str(item["id"]),
                kind=str(item["kind"]),
                title=str(item["title"]),
                amount=item.get("amount"),
                uplift_tenths=int(item["uplift_tenths"]),
                bank=item.get("bank"),
                rate=item.get("rate"),
                rate_type=item.get("rate_type"),
                rate_fuente=item.get("rate_fuente"),
            )
        )
    session.commit()
    saved = session.get(Proposal, proposal_id)
    assert saved is not None
    return to_payload(session, saved)


def delete_proposal(session: Session, proposal_id: str) -> bool:
    row = session.get(Proposal, proposal_id)
    if row is None:
        return False
    for child in session.exec(
        select(ProposalAction).where(ProposalAction.proposal_id == proposal_id)
    ).all():
        session.delete(child)
    for child in session.exec(
        select(ProposalFinancing).where(ProposalFinancing.proposal_id == proposal_id)
    ).all():
        session.delete(child)
    session.delete(row)
    session.commit()
    return True
