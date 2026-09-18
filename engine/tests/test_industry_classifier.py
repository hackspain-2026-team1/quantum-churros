from pathlib import Path

from xray_engine.industry_classifier import (
    CLASSIFIER_VERSION,
    RulesClassifierStrategy,
    build_company_signals,
    classify_dataset,
    dataset_fingerprint,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def test_dataset_fingerprint_is_stable() -> None:
    first = dataset_fingerprint(DATA_DIR)
    second = dataset_fingerprint(DATA_DIR)
    assert first == second
    assert len(first) == 64


def test_build_company_signals_covers_all_companies() -> None:
    signals = build_company_signals(DATA_DIR)
    assert signals.height == 1286
    assert "tx_collection_share" in signals.columns
    assert "invoice_ticket" in signals.columns


def test_classify_dataset_is_deterministic() -> None:
    hash_a, results_a = classify_dataset(DATA_DIR)
    hash_b, results_b = classify_dataset(DATA_DIR)
    assert hash_a == hash_b
    assert len(results_a) == len(results_b)
    assert results_a[0].classifier_version == CLASSIFIER_VERSION
    assert results_a[0].dataset_hash == hash_a


def test_known_logistics_archetype() -> None:
    _, results = classify_dataset(DATA_DIR)
    by_id = {item.entity_id: item for item in results}
    assert by_id["COMP_0542"].industry_slug == "logistics_supply_chain"


def test_known_marketing_archetype() -> None:
    _, results = classify_dataset(DATA_DIR)
    by_id = {item.entity_id: item for item in results}
    assert by_id["COMP_0825"].industry_slug == "marketing_advertising"


def test_comp_0680_treasury_profile() -> None:
    _, results = classify_dataset(DATA_DIR)
    comp = next(item for item in results if item.entity_id == "COMP_0680")
    assert comp.industry_slug == "business_services"
    assert comp.signals["tx_uncategorized_share"] > 0.4
