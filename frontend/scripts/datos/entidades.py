"""Índice reproducible de identidades ficticias para Rumbo.

Lee únicamente el bundle exportado por el motor. Los identificadores permanecen intactos y los nombres son una proyección de presentación estable, independiente del score y de la salud financiera.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "rumbo-entities-v1"
NAMING_VERSION = "rumbo-names-v1"

PREFIXES = (
    "Al",
    "Ar",
    "Bel",
    "Brav",
    "Cal",
    "Cen",
    "Dov",
    "El",
    "Fer",
    "Gal",
    "Iber",
    "Lun",
    "Mar",
    "Ner",
    "Nov",
    "Or",
    "Prad",
    "Riv",
    "Sol",
    "Val",
)
SUFFIXES = (
    "aria",
    "elia",
    "oria",
    "enia",
    "avia",
    "ira",
    "una",
    "esa",
    "onda",
    "ora",
    "edra",
    "alia",
    "iana",
)

SECTOR_DESCRIPTORS = {
    "business_services": "Servicios",
    "energy_utilities": "Energía",
    "financial_services": "Finanzas",
    "logistics_supply_chain": "Logística",
    "manufacturing": "Industrial",
    "marketing_advertising": "Comunicación",
    "professional_services": "Consultoría",
    "software": "Sistemas",
    "technology_services": "Tecnología",
}

UNIT_DESCRIPTORS = (
    "Operaciones",
    "Servicios",
    "Gestión",
    "Comercial",
    "Proyectos",
    "Desarrollo",
    "Soluciones",
    "Industria",
    "Logística",
    "Tecnología",
    "Capital",
    "Patrimonio",
    "Internacional",
    "Iberia",
    "Norte",
    "Centro",
    "Levante",
    "Atlántico",
    "Mediterráneo",
    "Europa",
    "Inversiones",
    "Infraestructuras",
    "Administración",
    "Participaciones",
)

LEGAL_FORMS = {
    "AD": ("S.L.",),
    "AE": ("L.L.C.",),
    "BE": ("B.V.", "S.R.L."),
    "DE": ("GmbH",),
    "DK": ("ApS",),
    "ES": ("S.L.", "S.L.U.", "S.A."),
    "FR": ("SAS", "SARL"),
    "GB": ("Ltd.",),
    "IT": ("S.r.l.", "S.p.A."),
    "MY": ("Sdn. Bhd.",),
    "NL": ("B.V.",),
    "NO": ("AS",),
    "PT": ("Lda.", "S.A."),
    "US": ("LLC", "Inc."),
}


def _entity_number(entity_id: str) -> int:
    match = re.search(r"(\d+)$", entity_id)
    if not match:
        return int.from_bytes(hashlib.sha256(entity_id.encode()).digest()[:4], "big")
    return int(match.group(1))


def brand_for(group_id: str) -> str:
    """Return a unique brand for sequential GROUP ids without relying on row order."""
    index = _entity_number(group_id) - 1
    if index < 0:
        index = 0
    capacity = len(PREFIXES) * len(SUFFIXES)
    slot = (index * 73) % capacity
    prefix = PREFIXES[slot % len(PREFIXES)]
    suffix = SUFFIXES[slot // len(PREFIXES)]
    cycle = index // capacity
    return f"{prefix}{suffix}{cycle + 1 if cycle else ''}"


def _profile(entity: dict[str, Any]) -> dict[str, Any]:
    return {item["key"]: item.get("value") for item in entity.get("profile", [])}


def _country_code(entity: dict[str, Any]) -> str | None:
    value = _profile(entity).get("country")
    match = re.search(r"\(([A-Z]{2})\)", value or "")
    return match.group(1) if match else None


def _legal_form(country: str | None, entity_id: str) -> str:
    options = LEGAL_FORMS.get(country or "", ("Ltd.",))
    return options[_entity_number(entity_id) % len(options)]


def _descriptor(company: dict[str, Any], position: int, total: int) -> str:
    role = company.get("role", "")
    if "tesorería" in role:
        return "Tesorería"
    if "financiación" in role:
        return "Financiación"
    if "sin actividad" in role:
        return "Participaciones"
    industry = company.get("context", {}).get("industry") or {}
    if total == 1 and float(industry.get("confidence", 0)) >= 0.65:
        return SECTOR_DESCRIPTORS.get(industry.get("slug"), "Servicios")
    return UNIT_DESCRIPTORS[position % len(UNIT_DESCRIPTORS)]


def build_entities(bundle: Path) -> dict[str, Any]:
    manifest = json.loads((bundle / "manifest.json").read_text())
    cut = manifest["months"][-1]
    groups: dict[str, Any] = {}
    companies: dict[str, Any] = {}

    for group_path in sorted((bundle / "groups").glob("*.json")):
        group = json.loads(group_path.read_text())
        group_id = group["id"]
        brand = brand_for(group_id)
        group_profile = _profile(group)
        industry = group.get("context", {}).get("industry") or {}
        summaries = sorted(group.get("companies", []), key=lambda item: item["id"])
        groups[group_id] = {
            "name": f"Grupo {brand}",
            "brand": brand,
            "country": _country_code(group),
            "industry": industry.get("slug"),
            "industry_label": industry.get("label"),
            "industry_confidence": industry.get("confidence"),
            "size": group_profile.get("size_band"),
            "n_companies": len(summaries),
        }

        used_descriptors: set[str] = set()
        for position, summary in enumerate(summaries):
            company_id = summary["id"]
            company = json.loads((bundle / "companies" / f"{company_id}.json").read_text())
            profile = _profile(company)
            month = next((item for item in company.get("months", []) if item["month"] == cut), None)
            country = _country_code(company) or groups[group_id]["country"]
            base_descriptor = _descriptor(company, position, len(summaries))
            descriptor = base_descriptor
            discriminator = position
            if descriptor in used_descriptors:
                descriptor = f"{base_descriptor} {UNIT_DESCRIPTORS[discriminator]}"
                while descriptor in used_descriptors:
                    discriminator = (discriminator + 1) % len(UNIT_DESCRIPTORS)
                    descriptor = f"{base_descriptor} {UNIT_DESCRIPTORS[discriminator]}"
            used_descriptors.add(descriptor)
            base_name = f"{brand} {descriptor}"
            companies[company_id] = {
                "name": base_name,
                "legal_name": f"{base_name}, {_legal_form(country, company_id)}",
                "group": group_id,
                "country": country,
                "role": company.get("role"),
                "size": profile.get("size_band"),
                "shown": month.get("shown") if month else None,
                "band": month.get("band") if month else None,
            }

    expected = manifest.get("counts", {})
    if expected.get("groups") not in (None, len(groups)):
        raise ValueError(
            f"Expected {expected['groups']} groups, generated {len(groups)}"
        )
    if expected.get("companies") not in (None, len(companies)):
        raise ValueError(
            f"Expected {expected['companies']} companies, generated {len(companies)}"
        )
    company_names = [company["name"] for company in companies.values()]
    if len(set(company_names)) != len(company_names):
        raise ValueError("Generated company names are not unique")

    vocabulary = json.dumps(
        {
            "prefixes": PREFIXES,
            "suffixes": SUFFIXES,
            "sectors": SECTOR_DESCRIPTORS,
            "units": UNIT_DESCRIPTORS,
            "legal_forms": LEGAL_FORMS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema": SCHEMA,
        "bundle_id": manifest["bundle_id"],
        "dataset_hash": manifest["dataset_hash"],
        "cut": cut,
        "naming_version": NAMING_VERSION,
        "vocabulary_hash": hashlib.sha256(vocabulary.encode()).hexdigest(),
        "groups": groups,
        "companies": companies,
    }


def write_atomic(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(output)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = build_entities(Path(args.bundle).expanduser())
    write_atomic(Path(args.out).expanduser(), payload)
    print(
        f"{len(payload['groups'])} grupos y {len(payload['companies'])} empresas "
        f"en el índice de entidades ({payload['naming_version']})."
    )


if __name__ == "__main__":
    main()
