import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_company_industry_returns_override_for_demo_company() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/companies/COMP_0680/industry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["industry_slug"] == "manufacturing"
    assert payload["source"] == "override"
    assert payload["confidence"] == 1.0


@pytest.mark.anyio
async def test_batch_industry_endpoint_returns_demo_companies() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/companies/industry",
            params={"ids": "COMP_0680,COMP_0218"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    slugs = {item["industry_slug"] for item in payload}
    assert "manufacturing" in slugs
    assert "logistics_supply_chain" in slugs


@pytest.mark.anyio
async def test_demo_payload_includes_industry_labels() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/demo")

    assert response.status_code == 200
    companies = response.json()["companies"]
    assert all("industry" in company for company in companies)
    velasco = next(item for item in companies if item["id"] == "COMP_0680")
    assert velasco["industry"]["industry_slug"] == "manufacturing"


@pytest.mark.anyio
async def test_industry_distribution_endpoint() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/industry/distribution")

    assert response.status_code == 200
    assert sum(response.json().values()) >= 1000
