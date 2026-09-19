import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _body(**extra):
    return {
        "id": "20260919-1200-abcd",
        "fecha": "2026-09-19T10:00:00+00:00",
        "kind": "company",
        "entidad": "COMP_0001",
        "grupoId": "GROUP_0147",
        "corte": "2026-08",
        "bundle_id": "aabbcc",
        "score_actual_tenths": 510,
        "acciones": [
            {
                "id": "a1",
                "pillar": "liquidity",
                "title": "Subir el colchón",
                "uplift_tenths": 54,
                "new_score_tenths": 564,
                "current": 15,
                "target": 21,
                "unit": "días",
            }
        ],
        "financiacion": [
            {
                "id": "f1",
                "kind": "factoring",
                "title": "Anticipar facturas",
                "amount": 160000,
                "uplift_tenths": 115,
                "bank": "Santander Rio Empresas",
                "rate": 6.0,
                "rate_type": "variable",
                "rate_fuente": "mercado",
            },
            {
                "id": "f1",
                "kind": "factoring",
                "title": "Anticipar facturas",
                "amount": 160000,
                "uplift_tenths": 115,
                "bank": "Banco Galicia Empresas",
                "rate": 6.0,
                "rate_type": "variable",
                "rate_fuente": "mercado",
            },
        ],
        **extra,
    }


@pytest.mark.anyio
async def test_proposal_roundtrip_keeps_history_and_banks() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/v1/proposals", json=_body())
        assert created.status_code == 200
        payload = created.json()
        assert payload["entidad"] == "COMP_0001"
        assert len(payload["acciones"]) == 1
        assert [x["bank"] for x in payload["financiacion"]] == [
            "Santander Rio Empresas",
            "Banco Galicia Empresas",
        ]

        listed = await client.get("/api/v1/proposals", params={"entity_id": "COMP_0001"})
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        one = await client.get("/api/v1/proposals/20260919-1200-abcd")
        assert one.status_code == 200
        assert one.json()["acciones"][0]["unit"] == "días"

        gone = await client.delete("/api/v1/proposals/20260919-1200-abcd")
        assert gone.status_code == 200
        assert (await client.get("/api/v1/proposals?entity_id=COMP_0001")).json() == []
