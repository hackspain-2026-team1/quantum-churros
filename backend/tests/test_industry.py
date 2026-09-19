import pytest
from app.main import app, engine
from app.models import EntityIndustry
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, delete
from xray_engine.industry_classifier import CLASSIFIER_VERSION, INDUSTRY_LABELS

DATASET_HASH = "synthetic-test-dataset"
SLUGS = sorted(INDUSTRY_LABELS)
# Synthetic companies: two in the first archetype, one in the second.
CLASSIFIED = {
    "COMP_T001": (SLUGS[0], 0.82),
    "COMP_T002": (SLUGS[0], 0.64),
    "COMP_T003": (SLUGS[1], 0.41),
}


@pytest.fixture(autouse=True)
def stored_classifications() -> None:
    with Session(engine) as session:
        session.exec(delete(EntityIndustry))
        for entity_id, (slug, confidence) in CLASSIFIED.items():
            session.add(
                EntityIndustry(
                    id=f"{DATASET_HASH}_{entity_id}_{CLASSIFIER_VERSION}",
                    dataset_hash=DATASET_HASH,
                    entity_id=entity_id,
                    industry_slug=slug,
                    industry_label=INDUSTRY_LABELS[slug],
                    confidence=confidence,
                    source="signals",
                    reason="synthetic test row",
                    classifier_version=CLASSIFIER_VERSION,
                    signals_json="{}",
                )
            )
        session.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_company_industry_is_the_stored_classification() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/companies/COMP_T001/industry")

    assert response.status_code == 200
    slug, confidence = CLASSIFIED["COMP_T001"]
    assert response.json() == {
        "entity_id": "COMP_T001",
        "industry_slug": slug,
        "industry_label": INDUSTRY_LABELS[slug],
        "confidence": confidence,
        "source": "signals",
        "reason": "synthetic test row",
        "classifier_version": CLASSIFIER_VERSION,
        "dataset_hash": DATASET_HASH,
    }


@pytest.mark.anyio
async def test_company_industry_is_404_when_unclassified() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/companies/COMP_T999/industry")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_batch_industry_keeps_request_order_and_skips_unknown_ids() -> None:
    async with _client() as client:
        response = await client.get(
            "/api/v1/companies/industry",
            params={"ids": "comp_t003, COMP_T999 ,COMP_T001"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["entity_id"] for item in payload] == ["COMP_T003", "COMP_T001"]
    assert [item["industry_slug"] for item in payload] == [SLUGS[1], SLUGS[0]]
    assert all(item["source"] == "signals" for item in payload)


@pytest.mark.anyio
async def test_industry_distribution_counts_stored_rows() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/industry/distribution")

    assert response.status_code == 200
    assert response.json() == {SLUGS[0]: 2, SLUGS[1]: 1}
