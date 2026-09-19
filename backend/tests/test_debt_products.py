import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_company_debt_products_demo_fixture() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/companies/COMP_0680/debt-products")
    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "COMP_0680"
    assert len(payload["products"]) >= 1
    assert payload["products"][0]["type_label"] == "Línea de crédito"


@pytest.mark.anyio
async def test_company_debt_products_empty_for_unknown_company() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/companies/COMP_9999/debt-products")
    assert response.status_code == 200
    assert response.json()["products"] == []
