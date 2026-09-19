from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import (
    AuditEvent,
    DisclosureGrant,
    FinancingCase,
    FundingNeed,
    IndicativeOffer,
    Mandate,
    Opportunity,
    Organization,
    OutboxEvent,
    ProviderCapability,
    utc_now,
)

from .policy import Principal, require_role
from .schemas import (
    AcceptOffer,
    AuthorizationCreate,
    CapabilityUpsert,
    CaseCreate,
    CloseCase,
    OfferCreate,
    ShortlistCreate,
)

TERMINAL_STATES = {"accepted", "closed"}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def active_until(expires_at: datetime, revoked_at: datetime | None) -> bool:
    return revoked_at is None and aware(expires_at) > utc_now()


def get_case(session: Session, case_id: str, *, lock: bool = False) -> FinancingCase:
    query = select(FinancingCase).where(FinancingCase.id == case_id)
    if lock:
        query = query.with_for_update()
    case = session.exec(query).one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Financing case not found")
    return case


def assert_version(case: FinancingCase, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != case.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Case changed", "current_version": case.version},
        )


def assert_case_actor(case: FinancingCase, principal: Principal, *roles: str) -> None:
    require_role(principal, *roles)
    if principal.role == "rumbo":
        return
    expected = (
        case.company_org_id if principal.role == "company" else case.consultant_org_id
    )
    if principal.organization_id != expected:
        raise HTTPException(
            status_code=403, detail="Case belongs to another organization"
        )


def record_event(
    session: Session,
    *,
    principal: Principal,
    case: FinancingCase | None,
    event_type: str,
    payload: dict[str, Any],
    visible_org_ids: list[str],
) -> None:
    event_id = new_id("evt")
    envelope = {
        **payload,
        "visible_org_ids": sorted(set(visible_org_ids)),
        "actor_role": principal.role,
    }
    session.add(
        AuditEvent(
            id=event_id,
            actor_id=principal.user_id,
            case_id=case.id if case else None,
            event_type=event_type,
            payload_json=envelope,
        )
    )
    session.add(
        OutboxEvent(
            id=new_id("out"),
            aggregate_type="financing_case" if case else "funding_need",
            aggregate_id=case.id
            if case
            else str(payload.get("funding_need_id", "portfolio")),
            event_type=event_type,
            payload_json={"event_id": event_id, **envelope},
        )
    )


def transition(case: FinancingCase, target: str, allowed: set[str]) -> None:
    if case.status not in allowed:
        raise HTTPException(
            status_code=409, detail=f"Cannot move case from {case.status} to {target}"
        )
    case.status = target
    case.version += 1
    case.updated_at = utc_now()


def detect_need(
    session: Session,
    principal: Principal,
    *,
    entity_id: str,
    score_snapshot_id: str,
    score: float,
    previous_score: float,
    amount_low: float,
    amount_high: float,
    needed_from: Any,
    needed_to: Any,
    confidence: float,
    source_month: Any,
    detected_since: Any,
    trajectory: str,
    trajectory_nature: str | None,
    model_version: str,
    params_hash: str,
    dataset_hash: str,
    explanation_method: str,
    drivers: dict[str, Any],
    profile: dict[str, Any],
) -> FundingNeed:
    require_role(principal, "rumbo")
    need = FundingNeed(
        id=new_id("need"),
        entity_id=entity_id,
        score_snapshot_id=score_snapshot_id,
        score=score,
        previous_score=previous_score,
        amount_low=amount_low,
        amount_high=amount_high,
        needed_from=needed_from,
        needed_to=needed_to,
        confidence=confidence,
        source_month=source_month,
        detected_since=detected_since,
        trajectory=trajectory,
        trajectory_nature=trajectory_nature,
        model_version=model_version,
        params_hash=params_hash,
        dataset_hash=dataset_hash,
        explanation_method=explanation_method,
        drivers_json=drivers,
        profile_json=profile,
    )
    session.add(need)
    record_event(
        session,
        principal=principal,
        case=None,
        event_type="funding_need.detected",
        payload={"funding_need_id": need.id, "entity_id": entity_id, "score": score},
        visible_org_ids=[],
    )
    session.commit()
    session.refresh(need)
    return need


def create_case(
    session: Session, principal: Principal, command: CaseCreate
) -> FinancingCase:
    require_role(principal, "consultant", "rumbo")
    need = session.get(FundingNeed, command.funding_need_id)
    if need is None:
        raise HTTPException(status_code=404, detail="Funding need not found")
    company = session.get(Organization, command.company_org_id)
    if company is None or company.kind != "company":
        raise HTTPException(status_code=422, detail="Company organization is invalid")
    case = FinancingCase(
        id=new_id("case"),
        funding_need_id=need.id,
        consultant_org_id=principal.organization_id,
        company_org_id=company.id,
        objective=command.objective,
        amount=command.amount,
        term_months=command.term_months,
        product_types_json=command.product_types,
    )
    need.status = "in_review"
    session.add(case)
    session.flush([case])
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="case.created",
        payload={"status": case.status},
        visible_org_ids=[case.consultant_org_id, case.company_org_id],
    )
    session.commit()
    session.refresh(case)
    return case


def authorize_case(
    session: Session,
    principal: Principal,
    case_id: str,
    command: AuthorizationCreate,
    expected_version: int | None,
) -> FinancingCase:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "company", "rumbo")
    assert_version(case, expected_version)
    if aware(command.expires_at) <= utc_now():
        raise HTTPException(
            status_code=422, detail="Authorization must expire in the future"
        )
    transition(case, "authorized", {"in_review"})
    session.add(
        Mandate(
            id=new_id("mandate"),
            case_id=case.id,
            scope_json=command.scope,
            granted_by=principal.user_id,
            expires_at=command.expires_at,
        )
    )
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="case.authorized",
        payload={"status": case.status, "version": case.version},
        visible_org_ids=[case.consultant_org_id, case.company_org_id],
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def publish_case(
    session: Session, principal: Principal, case_id: str, expected_version: int | None
) -> Opportunity:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "consultant", "rumbo")
    assert_version(case, expected_version)
    mandates = session.exec(select(Mandate).where(Mandate.case_id == case.id)).all()
    if not any(active_until(item.expires_at, item.revoked_at) for item in mandates):
        raise HTTPException(
            status_code=409, detail="Case has no active company authorization"
        )
    transition(case, "published", {"authorized"})
    need = session.get(FundingNeed, case.funding_need_id)
    if need is None:
        raise HTTPException(status_code=409, detail="Case funding need is missing")
    opportunity = Opportunity(
        id=new_id("opp"),
        case_id=case.id,
        public_code=f"RMB-{uuid4().hex[:8].upper()}",
        teaser_json={
            "score_band": score_band(need.score),
            "trajectory": need.trajectory,
            "trajectory_nature": need.trajectory_nature,
            "detected_since": need.detected_since.isoformat()
            if need.detected_since
            else None,
            "amount_range": [need.amount_low, need.amount_high],
            "needed_from": need.needed_from.isoformat(),
            "needed_to": need.needed_to.isoformat(),
            "confidence": need.confidence,
            "drivers": need.drivers_json,
            "profile": need.profile_json,
            "product_types": case.product_types_json,
        },
    )
    session.add_all([case, opportunity])
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="opportunity.published",
        payload={
            "opportunity_id": opportunity.id,
            "public_code": opportunity.public_code,
            "version": case.version,
        },
        visible_org_ids=[case.consultant_org_id, case.company_org_id],
    )
    session.commit()
    session.refresh(opportunity)
    return opportunity


def upsert_capability(
    session: Session, principal: Principal, command: CapabilityUpsert
) -> ProviderCapability:
    require_role(principal, "provider", "rumbo")
    existing = session.exec(
        select(ProviderCapability).where(
            ProviderCapability.provider_org_id == principal.organization_id,
            ProviderCapability.product_type == command.product_type,
        )
    ).one_or_none()
    if existing is None:
        existing = ProviderCapability(
            id=new_id("cap"),
            provider_org_id=principal.organization_id,
            product_type=command.product_type,
            eligibility_json=command.eligibility,
            terms_json=command.terms,
            active=command.active,
        )
    else:
        existing.eligibility_json = command.eligibility
        existing.terms_json = command.terms
        existing.active = command.active
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def compatible_opportunities(
    session: Session, principal: Principal
) -> list[dict[str, Any]]:
    require_role(principal, "provider", "rumbo")
    capabilities = session.exec(
        select(ProviderCapability).where(
            ProviderCapability.provider_org_id == principal.organization_id,
            ProviderCapability.active.is_(True),
        )
    ).all()
    rows: list[dict[str, Any]] = []
    for opportunity in session.exec(
        select(Opportunity).where(Opportunity.status == "open")
    ).all():
        case = get_case(session, opportunity.case_id)
        if case.status != "published":
            continue
        need = session.get(FundingNeed, case.funding_need_id)
        if need is None or not any(
            capability_matches(item, case, need) for item in capabilities
        ):
            continue
        own_offer = session.exec(
            select(IndicativeOffer).where(
                IndicativeOffer.opportunity_id == opportunity.id,
                IndicativeOffer.provider_org_id == principal.organization_id,
            )
        ).one_or_none()
        rows.append(
            {
                "opportunity": opportunity,
                "case_version": case.version,
                "teaser": opportunity.teaser_json,
                "own_offer": own_offer,
            }
        )
    return rows


def score_band(score: float) -> str:
    if score < 40:
        return "0–39"
    if score < 60:
        return "40–59"
    if score < 80:
        return "60–79"
    return "80–100"


def capability_matches(
    capability: ProviderCapability, case: FinancingCase, need: FundingNeed
) -> bool:
    if capability.product_type not in case.product_types_json:
        return False
    eligibility = capability.eligibility_json
    return need.score >= float(
        eligibility.get("score_min", 0)
    ) and case.amount <= float(eligibility.get("amount_max", float("inf")))


def submit_offer(
    session: Session, principal: Principal, opportunity_id: str, command: OfferCreate
) -> IndicativeOffer:
    require_role(principal, "provider", "rumbo")
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.status != "open":
        raise HTTPException(status_code=404, detail="Open opportunity not found")
    case = get_case(session, opportunity.case_id)
    if case.status != "published":
        raise HTTPException(status_code=409, detail="Case is not accepting offers")
    compatible = {
        row["opportunity"].id for row in compatible_opportunities(session, principal)
    }
    if opportunity.id not in compatible:
        raise HTTPException(
            status_code=403, detail="Provider capability does not match opportunity"
        )
    if aware(command.valid_until) <= utc_now():
        raise HTTPException(
            status_code=422, detail="Offer must remain valid in the future"
        )
    offer = session.exec(
        select(IndicativeOffer).where(
            IndicativeOffer.opportunity_id == opportunity.id,
            IndicativeOffer.provider_org_id == principal.organization_id,
        )
    ).one_or_none()
    if offer is None:
        offer = IndicativeOffer(
            id=new_id("offer"),
            opportunity_id=opportunity.id,
            provider_org_id=principal.organization_id,
            amount=command.amount,
            annual_rate=command.annual_rate,
            term_months=command.term_months,
            opening_fee=command.opening_fee,
            guarantee=command.guarantee,
            terms_json=command.terms,
            valid_until=command.valid_until,
        )
    else:
        offer.amount = command.amount
        offer.annual_rate = command.annual_rate
        offer.term_months = command.term_months
        offer.opening_fee = command.opening_fee
        offer.guarantee = command.guarantee
        offer.terms_json = command.terms
        offer.valid_until = command.valid_until
        offer.status = "submitted"
    session.add(offer)
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="offer.submitted",
        payload={"offer_id": offer.id, "provider_org_id": principal.organization_id},
        visible_org_ids=[
            case.consultant_org_id,
            case.company_org_id,
            principal.organization_id,
        ],
    )
    session.commit()
    session.refresh(offer)
    return offer


def shortlist(
    session: Session,
    principal: Principal,
    case_id: str,
    command: ShortlistCreate,
    expected_version: int | None,
) -> FinancingCase:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "company", "rumbo")
    assert_version(case, expected_version)
    if not command.provider_org_ids:
        raise HTTPException(status_code=422, detail="Choose at least one provider")
    if aware(command.expires_at) <= utc_now():
        raise HTTPException(
            status_code=422, detail="Disclosure must expire in the future"
        )
    opportunity = session.exec(
        select(Opportunity).where(Opportunity.case_id == case.id)
    ).one_or_none()
    if opportunity is None:
        raise HTTPException(status_code=409, detail="Case has no opportunity")
    offered = {
        item.provider_org_id
        for item in session.exec(
            select(IndicativeOffer).where(
                IndicativeOffer.opportunity_id == opportunity.id
            )
        ).all()
    }
    if not set(command.provider_org_ids).issubset(offered):
        raise HTTPException(
            status_code=422, detail="A shortlisted provider has not submitted an offer"
        )
    transition(case, "shortlisted", {"published"})
    for provider_org_id in sorted(set(command.provider_org_ids)):
        session.add(
            DisclosureGrant(
                id=new_id("grant"),
                case_id=case.id,
                grantee_org_id=provider_org_id,
                scope_json=command.scope,
                expires_at=command.expires_at,
            )
        )
        offer = session.exec(
            select(IndicativeOffer).where(
                IndicativeOffer.opportunity_id == opportunity.id,
                IndicativeOffer.provider_org_id == provider_org_id,
            )
        ).one()
        offer.status = "shortlisted"
        session.add(offer)
    session.add(case)
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="case.shortlisted",
        payload={"provider_org_ids": command.provider_org_ids, "version": case.version},
        visible_org_ids=[
            case.consultant_org_id,
            case.company_org_id,
            *command.provider_org_ids,
        ],
    )
    session.commit()
    session.refresh(case)
    return case


def accept_offer(
    session: Session,
    principal: Principal,
    case_id: str,
    command: AcceptOffer,
    expected_version: int | None,
) -> FinancingCase:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "company", "rumbo")
    assert_version(case, expected_version)
    offer = session.get(IndicativeOffer, command.offer_id)
    opportunity = session.exec(
        select(Opportunity).where(Opportunity.case_id == case.id)
    ).one_or_none()
    if (
        offer is None
        or opportunity is None
        or offer.opportunity_id != opportunity.id
        or offer.status != "shortlisted"
    ):
        raise HTTPException(
            status_code=422, detail="Offer is not shortlisted for this case"
        )
    transition(case, "accepted", {"shortlisted"})
    offer.status = "accepted"
    opportunity.status = "accepted"
    other_offers = session.exec(
        select(IndicativeOffer).where(
            IndicativeOffer.opportunity_id == opportunity.id,
            IndicativeOffer.id != offer.id,
        )
    ).all()
    for item in other_offers:
        item.status = "declined"
        session.add(item)
    session.add_all([case, offer, opportunity])
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="offer.accepted",
        payload={
            "offer_id": offer.id,
            "provider_org_id": offer.provider_org_id,
            "version": case.version,
        },
        visible_org_ids=[
            case.consultant_org_id,
            case.company_org_id,
            offer.provider_org_id,
        ],
    )
    session.commit()
    session.refresh(case)
    return case


def close_case(
    session: Session,
    principal: Principal,
    case_id: str,
    command: CloseCase,
    expected_version: int | None,
) -> FinancingCase:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "company", "consultant", "rumbo")
    assert_version(case, expected_version)
    transition(case, "closed", {"in_review", "authorized", "published", "shortlisted"})
    opportunity = session.exec(
        select(Opportunity).where(Opportunity.case_id == case.id)
    ).one_or_none()
    if opportunity:
        opportunity.status = "closed"
        session.add(opportunity)
    now = utc_now()
    grants = session.exec(
        select(DisclosureGrant).where(
            DisclosureGrant.case_id == case.id, DisclosureGrant.revoked_at.is_(None)
        )
    ).all()
    for grant in grants:
        grant.revoked_at = now
        session.add(grant)
    session.add(case)
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="case.closed",
        payload={"reason": command.reason, "version": case.version},
        visible_org_ids=[
            case.consultant_org_id,
            case.company_org_id,
            *(item.grantee_org_id for item in grants),
        ],
    )
    session.commit()
    session.refresh(case)
    return case


def revoke_disclosures(
    session: Session,
    principal: Principal,
    case_id: str,
    expected_version: int | None,
) -> FinancingCase:
    case = get_case(session, case_id, lock=True)
    assert_case_actor(case, principal, "company", "rumbo")
    assert_version(case, expected_version)
    transition(case, "closed", {"authorized", "published", "shortlisted"})
    now = utc_now()
    count = 0
    visible = [case.consultant_org_id, case.company_org_id]
    for grant in session.exec(
        select(DisclosureGrant).where(
            DisclosureGrant.case_id == case.id, DisclosureGrant.revoked_at.is_(None)
        )
    ).all():
        grant.revoked_at = now
        visible.append(grant.grantee_org_id)
        session.add(grant)
        count += 1
    for mandate in session.exec(
        select(Mandate).where(Mandate.case_id == case.id, Mandate.revoked_at.is_(None))
    ).all():
        mandate.revoked_at = now
        session.add(mandate)
        count += 1
    opportunity = session.exec(
        select(Opportunity).where(Opportunity.case_id == case.id)
    ).one_or_none()
    if opportunity is not None:
        opportunity.status = "closed"
        session.add(opportunity)
        for offer in session.exec(
            select(IndicativeOffer).where(
                IndicativeOffer.opportunity_id == opportunity.id,
                IndicativeOffer.status.in_(["submitted", "shortlisted"]),
            )
        ).all():
            offer.status = "declined"
            session.add(offer)
    session.add(case)
    record_event(
        session,
        principal=principal,
        case=case,
        event_type="access.revoked",
        payload={"count": count, "status": case.status, "version": case.version},
        visible_org_ids=visible,
    )
    session.commit()
    session.refresh(case)
    return case


def can_read_full_case(
    session: Session, case: FinancingCase, principal: Principal
) -> bool:
    if principal.role == "rumbo":
        return True
    if principal.role == "company":
        return principal.organization_id == case.company_org_id
    if principal.role == "consultant":
        return principal.organization_id == case.consultant_org_id
    if principal.role != "provider" or case.status not in {"shortlisted", "accepted"}:
        return False
    grants = session.exec(
        select(DisclosureGrant).where(
            DisclosureGrant.case_id == case.id,
            DisclosureGrant.grantee_org_id == principal.organization_id,
        )
    ).all()
    return any(active_until(item.expires_at, item.revoked_at) for item in grants)


def case_payload(
    session: Session, case: FinancingCase, principal: Principal
) -> dict[str, Any]:
    if not can_read_full_case(session, case, principal):
        raise HTTPException(
            status_code=403,
            detail="Case data has not been disclosed to this organization",
        )
    need = session.get(FundingNeed, case.funding_need_id)
    opportunity = session.exec(
        select(Opportunity).where(Opportunity.case_id == case.id)
    ).one_or_none()
    offers_query = (
        select(IndicativeOffer).where(IndicativeOffer.opportunity_id == opportunity.id)
        if opportunity is not None
        else None
    )
    if offers_query is not None and principal.role == "provider":
        offers_query = offers_query.where(
            IndicativeOffer.provider_org_id == principal.organization_id
        )
    offers = [] if offers_query is None else session.exec(offers_query).all()
    organizations = {
        item.id: item.name for item in session.exec(select(Organization)).all()
    }
    return {
        "case": case,
        "need": need,
        "opportunity": opportunity,
        "offers": [
            {
                "offer": offer,
                "provider_name": organizations.get(
                    offer.provider_org_id, offer.provider_org_id
                ),
            }
            for offer in offers
        ],
        "company_name": organizations.get(case.company_org_id, case.company_org_id),
        "consultant_name": organizations.get(
            case.consultant_org_id, case.consultant_org_id
        ),
    }


def workspace(session: Session, principal: Principal) -> dict[str, Any]:
    query = select(FinancingCase).order_by(FinancingCase.updated_at.desc())
    if principal.role == "company":
        query = query.where(FinancingCase.company_org_id == principal.organization_id)
    elif principal.role == "consultant":
        query = query.where(
            FinancingCase.consultant_org_id == principal.organization_id
        )
    elif principal.role == "provider":
        disclosed = [
            case_payload(session, case, principal)
            for case in session.exec(query).all()
            if can_read_full_case(session, case, principal)
        ]
        return {
            "role": principal.role,
            "opportunities": compatible_opportunities(session, principal),
            "cases": disclosed,
        }
    elif principal.role != "rumbo":
        raise HTTPException(status_code=403, detail="Unsupported role")
    cases = session.exec(query).all()
    return {
        "role": principal.role,
        "cases": [case_payload(session, case, principal) for case in cases],
        "opportunities": [],
    }
