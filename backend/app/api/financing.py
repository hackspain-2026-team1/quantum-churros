from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.demo_simulator import DEMO_IDENTITIES, start_fin_024
from app.events import hub
from app.financing.policy import Principal, current_principal
from app.financing.schemas import (
    AcceptOffer,
    AuthorizationCreate,
    CapabilityUpsert,
    CloseCase,
    OfferCreate,
    ShortlistCreate,
)
from app.financing.service import (
    accept_offer,
    authorize_case,
    case_payload,
    close_case,
    get_case,
    publish_case,
    revoke_disclosures,
    shortlist,
    submit_offer,
    upsert_capability,
    workspace,
)

router = APIRouter(prefix="/api/v1/financing", tags=["financing"])


@router.get("/workspace")
def get_workspace(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return workspace(session, principal)


@router.get("/cases/{case_id}")
def get_financing_case(
    case_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return case_payload(session, get_case(session, case_id), principal)


@router.post("/cases/{case_id}/authorize")
def authorize(
    case_id: str,
    command: AuthorizationCreate,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return authorize_case(session, principal, case_id, command, expected_version)


@router.post("/cases/{case_id}/publish")
def publish(
    case_id: str,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return publish_case(session, principal, case_id, expected_version)


@router.post("/capabilities")
def capability(
    command: CapabilityUpsert,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return upsert_capability(session, principal, command)


@router.post("/opportunities/{opportunity_id}/offers")
def offer(
    opportunity_id: str,
    command: OfferCreate,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return submit_offer(session, principal, opportunity_id, command)


@router.post("/cases/{case_id}/shortlist")
def shortlist_case(
    case_id: str,
    command: ShortlistCreate,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return shortlist(session, principal, case_id, command, expected_version)


@router.post("/cases/{case_id}/accept")
def accept(
    case_id: str,
    command: AcceptOffer,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return accept_offer(session, principal, case_id, command, expected_version)


@router.post("/cases/{case_id}/close")
def close(
    case_id: str,
    command: CloseCase,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return close_case(session, principal, case_id, command, expected_version)


@router.post("/cases/{case_id}/revoke")
def revoke(
    case_id: str,
    expected_version: int | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
):
    return revoke_disclosures(session, principal, case_id, expected_version)


@router.get("/events")
def events(principal: Principal = Depends(current_principal)) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        async with hub.subscribe() as queue:
            yield "retry: 1500\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                visible = event.get("payload", {}).get("visible_org_ids", [])
                if (
                    principal.role != "rumbo"
                    and principal.organization_id not in visible
                ):
                    continue
                yield f"id: {event['id']}\nevent: financing\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/demo/identities")
def demo_identities() -> dict[str, object]:
    if not settings.financing_demo_enabled:
        raise HTTPException(status_code=404, detail="Demo profile is disabled")
    return {"scenario": "FIN-024", "identities": DEMO_IDENTITIES}


@router.post("/demo/FIN-024/start")
def start_demo(session: Session = Depends(get_session)) -> dict[str, object]:
    if not settings.financing_demo_enabled:
        raise HTTPException(status_code=404, detail="Demo profile is disabled")
    return start_fin_024(session)
