import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from entidades import NAMING_VERSION, brand_for, build_entities


def test_brands_are_stable_and_unique_for_challenge_groups() -> None:
    brands = [brand_for(f"GROUP_{number:04d}") for number in range(1, 251)]
    assert len(set(brands)) == 250
    assert brand_for("GROUP_0046") == brands[45]


def test_generated_entities_keep_ids_and_group_families(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    (bundle / "groups").mkdir(parents=True)
    (bundle / "companies").mkdir()
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_id": "bundle-test",
                "dataset_hash": "dataset-test",
                "months": ["2026-08"],
            }
        )
    )
    profile = [
        {"key": "country", "value": "España (ES)"},
        {"key": "size_band", "value": "Pequeña (2-10 M€)"},
    ]
    companies = [
        {"id": "COMP_0001", "role": "Centro de tesorería del grupo"},
        {"id": "COMP_0002", "role": "Centro de tesorería del grupo"},
    ]
    group = {
        "id": "GROUP_0001",
        "context": {
            "industry": {
                "slug": "business_services",
                "label": "Servicios empresariales",
                "confidence": 0.4,
            }
        },
        "profile": profile,
        "companies": companies,
    }
    (bundle / "groups" / "GROUP_0001.json").write_text(json.dumps(group))
    for company in companies:
        entity = {
            **company,
            "context": group["context"],
            "profile": profile,
            "months": [{"month": "2026-08", "shown": 500, "band": "watch"}],
        }
        (bundle / "companies" / f"{company['id']}.json").write_text(
            json.dumps(entity)
        )

    payload = build_entities(bundle)
    assert payload["naming_version"] == NAMING_VERSION
    assert set(payload["groups"]) == {"GROUP_0001"}
    assert set(payload["companies"]) == {"COMP_0001", "COMP_0002"}
    assert len({company["name"] for company in payload["companies"].values()}) == 2
    for company_id, company in payload["companies"].items():
        group = payload["groups"][company["group"]]
        assert company["name"].startswith(group["brand"])
        assert company_id.startswith("COMP_")

    first_names = {
        entity_id: company["name"]
        for entity_id, company in payload["companies"].items()
    }
    company_path = bundle / "companies" / "COMP_0001.json"
    changed = json.loads(company_path.read_text())
    changed["months"][0]["shown"] = 999
    changed["months"][0]["band"] = "solid"
    company_path.write_text(json.dumps(changed))
    rescored = build_entities(bundle)
    assert {
        entity_id: company["name"]
        for entity_id, company in rescored["companies"].items()
    } == first_names
