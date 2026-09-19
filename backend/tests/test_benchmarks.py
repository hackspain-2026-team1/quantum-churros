import pytest
from app.benchmarks.tesorio_ar_2025 import INDUSTRY_METRICS, STUDY_ID
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_list_benchmarks_includes_tesorio_study() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/benchmarks")

    assert response.status_code == 200
    studies = response.json()
    assert any(study["id"] == STUDY_ID for study in studies)


@pytest.mark.anyio
async def test_get_tesorio_benchmark_returns_industry_metrics() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/benchmarks/{STUDY_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "tesorio"
    assert payload["data_period"] == "Q4 2024"
    assert len(payload["industries"]) == len(INDUSTRY_METRICS)
    assert payload["industries"][0]["industry"] == "Financial Services"
    assert payload["industries"][0]["open_ar_overdue_ratio"] == 0.11


@pytest.mark.anyio
async def test_get_benchmark_returns_404_for_unknown_study() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/benchmarks/UNKNOWN_STUDY")

    assert response.status_code == 404
