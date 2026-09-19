from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session

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

# Products of the most recent completed import of ``source.debt_products``.
PRODUCTS_QUERY = text(
    """
    SELECT product_id, type, label, bank_name, currency, granted, outstanding
    FROM source.debt_products
    WHERE upper(company_id) = :company_id
      AND dataset_hash = (
        SELECT dataset_hash FROM source.dataset_import
        WHERE status = 'completed' ORDER BY completed_at DESC LIMIT 1
      )
    ORDER BY product_id
    """
)


def _amount(value: float | None) -> float | None:
    return None if value is None else abs(float(value))


def _row_to_product(row: Mapping[str, object]) -> DebtProductRead:
    product_type = str(row["type"])
    return DebtProductRead(
        product_id=row["product_id"],
        type=product_type,
        type_label=TYPE_LABELS.get(product_type, product_type.replace("_", " ").title()),
        label=row["label"],
        bank_name=row["bank_name"],
        currency=row["currency"],
        granted=_amount(row["granted"]),
        outstanding=_amount(row["outstanding"]),
    )


def list_debt_products(session: Session, entity_id: str) -> list[DebtProductRead]:
    try:
        rows = session.execute(PRODUCTS_QUERY, {"company_id": entity_id.upper()}).mappings().all()
    except (OperationalError, ProgrammingError):
        # the source schema does not exist until a dataset has been ingested
        session.rollback()
        return []
    return [_row_to_product(row) for row in rows]
