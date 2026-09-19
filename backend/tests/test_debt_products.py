import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_debt_products_are_read_from_the_source_schema(tmp_path) -> None:
    from app.debt_products import list_debt_products
    from sqlalchemy import text
    from sqlmodel import Session, create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'main.db'}")
    with Session(engine) as session:
        session.execute(text(f"ATTACH DATABASE '{tmp_path / 'source.db'}' AS source"))
        session.execute(text("CREATE TABLE source.dataset_import (dataset_hash, status, completed_at)"))
        session.execute(
            text(
                "CREATE TABLE source.debt_products "
                "(dataset_hash, product_id, company_id, type, label, bank_name, currency, granted, outstanding)"
            )
        )
        session.execute(text("INSERT INTO source.dataset_import VALUES ('old', 'completed', 1), ('new', 'completed', 2)"))
        session.execute(
            text(
                "INSERT INTO source.debt_products VALUES "
                "('old', 'P0', 'COMP_T001', 'loan', 'Viejo', 'Banco', 'EUR', -5, -5), "
                "('new', 'P1', 'COMP_T001', 'lineofcredit', 'Poliza', 'Banco', 'EUR', -1000, -400)"
            )
        )
        products = list_debt_products(session, "comp_t001")
    engine.dispose()
    assert [p.type_label for p in products] == ["Línea de crédito"]
    assert products[0].granted == 1000


@pytest.mark.anyio
async def test_company_debt_products_empty_for_unknown_company() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/companies/COMP_9999/debt-products")
    assert response.status_code == 200
    assert response.json()["products"] == []
