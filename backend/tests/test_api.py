import pytest
from app.main import app, engine
from app.models import BenchmarkStudy, Entity, RecommendedAction, Workspace
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, select


@pytest.mark.anyio
async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}


def test_api_surface_is_bundle_plus_context() -> None:
    assert set(app.openapi()["paths"]) == {
        "/health",
        "/api/v1/bundle/{path}",
        "/api/v1/benchmarks",
        "/api/v1/benchmarks/{study_id}",
        "/api/v1/companies/{entity_id}/debt-products",
        "/api/v1/companies/{entity_id}/industry",
        "/api/v1/companies/industry",
        "/api/v1/industry/distribution",
        "/api/v1/scores/{entity_id}",
        "/api/v1/proposals",
        "/api/v1/proposals/{proposal_id}",
        "/api/v1/financing/workspace",
        "/api/v1/financing/cases/{case_id}",
        "/api/v1/financing/cases/{case_id}/authorize",
        "/api/v1/financing/cases/{case_id}/publish",
        "/api/v1/financing/cases/{case_id}/shortlist",
        "/api/v1/financing/cases/{case_id}/accept",
        "/api/v1/financing/cases/{case_id}/close",
        "/api/v1/financing/cases/{case_id}/revoke",
        "/api/v1/financing/capabilities",
        "/api/v1/financing/opportunities/{opportunity_id}/offers",
        "/api/v1/financing/events",
        "/api/v1/financing/demo/identities",
        "/api/v1/financing/demo/FIN-024/start",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/demo"),
        ("POST", "/api/v1/scenarios"),
        ("GET", "/api/v1/actions"),
    ],
)
async def test_retired_demo_endpoints_are_gone(method: str, path: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_scores_of_an_unknown_entity_are_empty() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/scores/COMP_DOES_NOT_EXIST")
    assert response.status_code == 200
    assert response.json() == []


def test_startup_seeds_reference_studies_and_nothing_else() -> None:
    with TestClient(app) as client:  # the context manager runs the lifespan
        assert client.get("/health").status_code == 200

    with Session(engine) as session:
        assert session.exec(select(BenchmarkStudy)).first() is not None
        for table in (Workspace, Entity, RecommendedAction):
            assert session.exec(select(table)).all() == [], table.__name__
