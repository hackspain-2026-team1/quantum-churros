from sqlmodel import Session, select

from .config import settings
from .financing.policy import Principal
from .financing.schemas import CapabilityUpsert, CaseCreate
from .financing.service import create_case, detect_need, upsert_capability, workspace
from .financing.signals import load_financing_signal
from .models import Membership, Organization

DEMO_IDENTITIES = {
    "consultant": {
        "user_id": "demo-consultant",
        "organization_id": "org-rumbo-advisory",
        "role": "consultant",
    },
    "company": {
        "user_id": "demo-company",
        "organization_id": "org-cenonda",
        "role": "company",
    },
    "provider": {
        "user_id": "demo-provider",
        "organization_id": "org-norte-capital",
        "role": "provider",
    },
    "provider_alt": {
        "user_id": "demo-provider-atlas",
        "organization_id": "org-atlas-bank",
        "role": "provider",
    },
}


def principal(name: str) -> Principal:
    return Principal(**DEMO_IDENTITIES[name])


def ensure_demo_identity(
    session: Session, name: str, kind: str, organization_name: str
) -> None:
    actor = principal(name)
    organization = session.get(Organization, actor.organization_id)
    if organization is None:
        organization = Organization(
            id=actor.organization_id, kind=kind, name=organization_name
        )
    else:
        organization.kind = kind
        organization.name = organization_name
    session.add(organization)
    membership = session.exec(
        select(Membership).where(
            Membership.organization_id == actor.organization_id,
            Membership.user_id == actor.user_id,
            Membership.role == actor.role,
        )
    ).one_or_none()
    if membership is None:
        session.add(
            Membership(
                id=f"membership-{name}",
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                role=actor.role,
            )
        )


def start_fin_024(session: Session) -> dict[str, object]:
    signal = load_financing_signal(settings.bundle_dir, settings.entity_aliases_path)
    ensure_demo_identity(session, "consultant", "consultant", "Rumbo Advisory")
    ensure_demo_identity(session, "company", "company", signal.company_name)
    ensure_demo_identity(session, "provider", "provider", "Norte Capital")
    ensure_demo_identity(session, "provider_alt", "provider", "Banco Atlas")
    session.commit()

    for provider_name in ("provider", "provider_alt"):
        actor = principal(provider_name)
        upsert_capability(
            session,
            actor,
            CapabilityUpsert(
                product_type="linea_credito",
                eligibility={"amount_max": 1000000, "score_min": 30},
                terms={"term_months": [12, 24, 36]},
            ),
        )

    engine_actor = Principal(
        user_id="demo-engine", organization_id="rumbo", role="rumbo"
    )
    need = detect_need(
        session,
        engine_actor,
        entity_id=signal.entity_id,
        score_snapshot_id=signal.score_snapshot_id,
        score=signal.score,
        previous_score=signal.previous_score,
        amount_low=signal.amount_low,
        amount_high=signal.amount_high,
        needed_from=signal.needed_from,
        needed_to=signal.needed_to,
        confidence=signal.confidence,
        source_month=signal.source_month,
        detected_since=signal.detected_since,
        trajectory=signal.trajectory,
        trajectory_nature=signal.trajectory_nature,
        model_version=signal.model_version,
        params_hash=signal.params_hash,
        dataset_hash=signal.dataset_hash,
        explanation_method="exact_additive",
        drivers=signal.drivers,
        profile=signal.profile,
    )
    case = create_case(
        session,
        principal("consultant"),
        CaseCreate(
            funding_need_id=need.id,
            company_org_id=principal("company").organization_id,
            objective="Reforzar el colchón de liquidez ante el deterioro estructural detectado",
            amount=signal.amount,
            term_months=12,
            product_types=signal.product_types,
        ),
    )
    return {
        "scenario": "FIN-024",
        "case_id": case.id,
        "identities": DEMO_IDENTITIES,
        "workspace": workspace(session, principal("consultant")),
    }
