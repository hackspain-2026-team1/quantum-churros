import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}


@pytest.mark.anyio
async def test_scenario_preserves_observed_score() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/scenarios",
            json={
                "collection_days": 12,
                "refinance_amount": 180000,
                "payment_extension_days": 7,
            },
        )
    assert response.status_code == 200
    assert 0 <= response.json()["base_score"] <= 100
    assert response.json()["projected_score"] > response.json()["base_score"]
