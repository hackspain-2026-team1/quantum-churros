"""Core profile card: who the entity is, inferred, with evidence and coverage.

Product surface and gates only. Nothing here feeds pillars or the aggregate;
the industry archetype is attached as ``context["industry"]`` and nowhere else.
Every rule is deterministic and uses the rows of the entity (or of its group)
plus ``Params``: a card does not change with the rest of the cohort.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from .cleaning import CleanTables
from .contracts import IndustryClassification, Params, ProfileCard

PROFILE_LABELS: dict[str, str] = {
    "country": "País",
    "size_band": "Tamaño",
    "erp_tier": "ERP y facturas",
    "group_role": "Rol en el grupo",
    "treasury_structure": "Estructura de tesorería",
    "financing_profile": "Financiación y holgura",
    "history_depth": "Profundidad de historia",
    "seasonality": "Estacionalidad",
    "customer_concentration": "Concentración de clientes",
    "payment_policy": "Política de pago",
    "revenue_model": "Modelo de ingreso",
    "data_quality": "Calidad de dato",
}


def build_profiles(
    clean: CleanTables,
    panel: pl.DataFrame,
    params: Params,
    industry: Mapping[str, IndustryClassification] | None = None,
) -> dict[str, ProfileCard]:
    """One card per company and per group, keyed by entity_id, as of
    ``clean.window.last_month``.

    ``attributes`` follow ``PROFILE_KEYS`` order, one ``ProfileAttribute`` per
    key, always present: an attribute that cannot be inferred has ``value``
    None and ``coverage`` 0. ``evidence`` is a Spanish sentence built from
    aggregates (counts, shares, amounts), never from a raw description.
    ``panel`` follows ``PANEL_COLUMNS``. ``industry`` maps company_id to its
    classification; it lands in ``context["industry"]`` (slug, label,
    confidence, reason) for companies and as the modal member slug for groups.
    """
    raise NotImplementedError
