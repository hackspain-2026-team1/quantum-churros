import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_debt_products_are_read_from_the_dataset(tmp_path, monkeypatch) -> None:
    from app import debt_products
    from app.config import settings

    (tmp_path / "debt_products.csv").write_text(
        "product_id,company_id,type,label,bank_name,currency,granted,outstanding\n"
        "P1,COMP_T001,lineofcredit,Poliza,Banco,EUR,-1000,-400\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    debt_products._load_all_products.cache_clear()
    products = debt_products.list_debt_products("comp_t001")
    debt_products._load_all_products.cache_clear()
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
