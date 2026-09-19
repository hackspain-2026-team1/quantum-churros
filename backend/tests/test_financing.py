import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


def headers(identity: dict[str, str], version: int | None = None) -> dict[str, str]:
    result = {
        "X-Rumbo-User": identity["user_id"],
        "X-Rumbo-Organization": identity["organization_id"],
        "X-Rumbo-Role": identity["role"],
    }
    if version is not None:
        result["If-Match"] = str(version)
    return result


@pytest.fixture
def financing_bundle(tmp_path: Path, monkeypatch: Any) -> Path:
    bundle = tmp_path / "bundle"
    groups = bundle / "groups"
    groups.mkdir(parents=True)
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "engine_version": "engine-test-v2",
                "params_hash": "params-test",
                "dataset_hash": "dataset-test",
            }
        ),
        encoding="utf-8",
    )
    (groups / "GROUP_TEST.json").write_text(
        json.dumps(
            {
                "id": "GROUP_TEST",
                "months": [
                    {"month": "2026-07", "shown": 512},
                    {
                        "month": "2026-08",
                        "shown": 455,
                        "feed_live": True,
                        "abstain": None,
                        "conf": {"value": 0.91},
                        "verdict": {
                            "direction": "deteriorating",
                            "nature": "structural",
                            "detected_since": "2026-06",
                        },
                        "pillars": [
                            {
                                "key": "liquidity",
                                "contrib": -73,
                                "note": "El colchón de caja se ha reducido de forma persistente.",
                            },
                            {
                                "key": "collections",
                                "contrib": -41,
                                "note": "Los cobros llegan más tarde que en el trimestre anterior.",
                            },
                        ],
                        "actions": [
                            {
                                "id": "liquidity-buffer",
                                "pillar": "liquidity",
                                "current": 11,
                                "target": 35,
                                "amount_eur": 285000,
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    aliases = tmp_path / "entities.json"
    aliases.write_text(
        json.dumps(
            {
                "groups": {
                    "GROUP_TEST": {
                        "name": "Grupo Maravia",
                        "country": "ES",
                        "industry_label": "Marketing y publicidad",
                        "size": "Pequeña",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "bundle_dir", bundle)
    monkeypatch.setattr(settings, "entity_aliases_path", aliases)
    return bundle


@pytest.mark.anyio
async def test_financing_workspace_requires_identity() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/financing/workspace")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_fin_024_runs_through_authorization_market_and_acceptance(
    monkeypatch: Any, financing_bundle: Path
) -> None:
    monkeypatch.setattr(settings, "financing_demo_enabled", True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        started = await client.post("/api/v1/financing/demo/FIN-024/start")
        assert started.status_code == 200, started.text
        payload = started.json()
        case_id = payload["case_id"]
        identities = payload["identities"]

        consultant_workspace = payload["workspace"]
        need = consultant_workspace["cases"][0]["need"]
        assert need["entity_id"] == "GROUP_TEST"
        assert need["score"] == 45.5
        assert need["model_version"] == "engine-test-v2"
        assert need["explanation_method"] == "exact_additive"

        company = identities["company"]
        consultant = identities["consultant"]
        provider = identities["provider"]
        provider_alt = identities["provider_alt"]
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()

        authorized = await client.post(
            f"/api/v1/financing/cases/{case_id}/authorize",
            headers=headers(company, 1),
            json={
                "scope": {"providers": "compatible", "identity": "shortlist_only"},
                "expires_at": expires_at,
            },
        )
        assert authorized.status_code == 200, authorized.text
        assert authorized.json()["status"] == "authorized"

        stale = await client.post(
            f"/api/v1/financing/cases/{case_id}/publish", headers=headers(consultant, 1)
        )
        assert stale.status_code == 409

        published = await client.post(
            f"/api/v1/financing/cases/{case_id}/publish", headers=headers(consultant, 2)
        )
        assert published.status_code == 200, published.text
        opportunity_id = published.json()["id"]

        for identity, rate in ((provider, 0.054), (provider_alt, 0.059)):
            offered = await client.post(
                f"/api/v1/financing/opportunities/{opportunity_id}/offers",
                headers=headers(identity),
                json={
                    "amount": 100000,
                    "annual_rate": rate,
                    "term_months": 12,
                    "opening_fee": 0.005,
                    "guarantee": "Sin garantía personal",
                    "terms": {"amortization": "monthly"},
                    "valid_until": expires_at,
                },
            )
            assert offered.status_code == 200, offered.text

        company_workspace = await client.get(
            "/api/v1/financing/workspace", headers=headers(company)
        )
        offers = company_workspace.json()["cases"][0]["offers"]
        selected_offer = next(
            item["offer"]
            for item in offers
            if item["offer"]["provider_org_id"] == provider["organization_id"]
        )

        shortlisted = await client.post(
            f"/api/v1/financing/cases/{case_id}/shortlist",
            headers=headers(company, 3),
            json={
                "provider_org_ids": [provider["organization_id"]],
                "scope": {
                    "identity": True,
                    "operations": "aggregated",
                    "documents": ["KYC"],
                },
                "expires_at": expires_at,
            },
        )
        assert shortlisted.status_code == 200, shortlisted.text
        assert shortlisted.json()["status"] == "shortlisted"

        provider_workspace = await client.get(
            "/api/v1/financing/workspace", headers=headers(provider)
        )
        assert provider_workspace.status_code == 200
        assert provider_workspace.json()["opportunities"] == []
        assert provider_workspace.json()["cases"][0]["company_name"] == "Grupo Maravia"
        assert len(provider_workspace.json()["cases"][0]["offers"]) == 1

        disclosed = await client.get(
            f"/api/v1/financing/cases/{case_id}", headers=headers(provider)
        )
        hidden = await client.get(
            f"/api/v1/financing/cases/{case_id}", headers=headers(provider_alt)
        )
        assert disclosed.status_code == 200
        assert hidden.status_code == 403

        accepted = await client.post(
            f"/api/v1/financing/cases/{case_id}/accept",
            headers=headers(company, 4),
            json={"offer_id": selected_offer["id"]},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "accepted"


@pytest.mark.anyio
async def test_revocation_closes_market_and_removes_provider_access(
    monkeypatch: Any, financing_bundle: Path
) -> None:
    monkeypatch.setattr(settings, "financing_demo_enabled", True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = (await client.post("/api/v1/financing/demo/FIN-024/start")).json()
        case_id = payload["case_id"]
        identities = payload["identities"]
        company = identities["company"]
        consultant = identities["consultant"]
        provider = identities["provider"]
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()

        await client.post(
            f"/api/v1/financing/cases/{case_id}/authorize",
            headers=headers(company, 1),
            json={"scope": {"providers": "compatible"}, "expires_at": expires_at},
        )
        await client.post(
            f"/api/v1/financing/cases/{case_id}/publish",
            headers=headers(consultant, 2),
        )
        before = await client.get(
            "/api/v1/financing/workspace", headers=headers(provider)
        )
        assert any(
            item["opportunity"]["case_id"] == case_id
            for item in before.json()["opportunities"]
        )

        revoked = await client.post(
            f"/api/v1/financing/cases/{case_id}/revoke",
            headers=headers(company, 3),
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["status"] == "closed"

        after = await client.get(
            "/api/v1/financing/workspace", headers=headers(provider)
        )
        assert all(
            item["opportunity"]["case_id"] != case_id
            for item in after.json()["opportunities"]
        )
        disclosed = await client.get(
            f"/api/v1/financing/cases/{case_id}", headers=headers(provider)
        )
        assert disclosed.status_code == 403
