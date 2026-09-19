from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from .config import settings
from .models import DebtProductRead

TYPE_LABELS: dict[str, str] = {
    "loan": "Préstamo",
    "lineofcredit": "Línea de crédito",
    "factoring": "Factoring",
    "confirming": "Confirming",
    "leasing": "Leasing",
    "guarantee": "Aval",
    "mortgage": "Hipoteca",
    "renting": "Renting",
}

DEMO_DEBT_PRODUCTS: dict[str, list[DebtProductRead]] = {
    "COMP_0680": [
        DebtProductRead(
            product_id="DEMO_LOC_0680",
            type="lineofcredit",
            type_label="Línea de crédito",
            label="Circulante Velasco",
            bank_name="CaixaBank",
            currency="EUR",
            granted=800_000,
            outstanding=648_000,
        ),
        DebtProductRead(
            product_id="DEMO_CF_0680",
            type="confirming",
            type_label="Confirming",
            label="Confirming proveedores",
            bank_name="CaixaBank",
            currency="EUR",
            granted=250_000,
            outstanding=42_000,
        ),
    ],
}


def _parse_amount(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return abs(float(value))


def _row_to_product(row: dict[str, str]) -> DebtProductRead:
    product_type = row["type"]
    return DebtProductRead(
        product_id=row["product_id"],
        type=product_type,
        type_label=TYPE_LABELS.get(product_type, product_type.replace("_", " ").title()),
        label=row["label"],
        bank_name=row["bank_name"],
        currency=row["currency"],
        granted=_parse_amount(row.get("granted")),
        outstanding=_parse_amount(row.get("outstanding")),
    )


@lru_cache(maxsize=1)
def _load_all_products(data_dir: str) -> dict[str, list[DebtProductRead]]:
    path = Path(data_dir) / "debt_products.csv"
    if not path.exists():
        return {}
    by_company: dict[str, list[DebtProductRead]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            company_id = row["company_id"].upper()
            by_company.setdefault(company_id, []).append(_row_to_product(row))
    return by_company


def list_debt_products(entity_id: str) -> list[DebtProductRead]:
    normalized = entity_id.upper()
    demo_products = DEMO_DEBT_PRODUCTS.get(normalized)
    if demo_products is not None:
        return demo_products
    return _load_all_products(str(settings.data_dir.resolve())).get(normalized, [])
