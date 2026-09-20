import json
from pathlib import Path

import pytest
from app.static_data import StaticDataError, verify_static_data


BUNDLE_ID = "a" * 64


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def static_data(tmp_path: Path) -> tuple[Path, Path]:
    bundle = tmp_path / "bundle"
    rumbo = tmp_path / "rumbo"
    _write(
        bundle / "manifest.json",
        {"schema": "xray-export-v1", "bundle_id": BUNDLE_ID, "counts": {"groups": 1, "companies": 2}},
    )
    _write(rumbo / "params.json", {"schema": "rumbo-params-v1", "bundle_id": BUNDLE_ID})
    _write(
        rumbo / "entities.json",
        {"schema": "rumbo-entities-v1", "bundle_id": BUNDLE_ID, "groups": {"g": {}}, "companies": {"a": {}, "b": {}}},
    )
    _write(rumbo / "products" / "index.json", {"schema": "rumbo-products-index-v1", "bundle_id": BUNDLE_ID})
    _write(rumbo / "horizons" / "index.json", {"schema": "rumbo-horizons-index-v1", "bundle_id": BUNDLE_ID})
    return bundle, rumbo


def test_accepts_complete_data_from_one_bundle(static_data: tuple[Path, Path]) -> None:
    result = verify_static_data(*static_data)

    assert result.bundle_id == BUNDLE_ID
    assert len(result.checked_files) == 5
    assert result.warnings == ()


def test_rejects_a_missing_derived_file(static_data: tuple[Path, Path]) -> None:
    bundle, rumbo = static_data
    (rumbo / "entities.json").unlink()

    with pytest.raises(StaticDataError, match="Missing static data file"):
        verify_static_data(bundle, rumbo)


def test_rejects_a_derived_file_from_another_bundle(static_data: tuple[Path, Path]) -> None:
    bundle, rumbo = static_data
    _write(rumbo / "params.json", {"schema": "rumbo-params-v1", "bundle_id": "b" * 64})

    with pytest.raises(StaticDataError, match="Bundle mismatch"):
        verify_static_data(bundle, rumbo)


def test_accepts_legacy_products_with_an_explicit_warning(static_data: tuple[Path, Path]) -> None:
    bundle, rumbo = static_data
    _write(rumbo / "products" / "index.json", {"schema": "rumbo-products-index-v1"})

    result = verify_static_data(bundle, rumbo)

    assert result.warnings == (
        f"{rumbo / 'products' / 'index.json'} has no bundle_id; regenerate products with the current generator",
    )


def test_rejects_entity_counts_that_do_not_match_the_manifest(static_data: tuple[Path, Path]) -> None:
    bundle, rumbo = static_data
    _write(
        rumbo / "entities.json",
        {"schema": "rumbo-entities-v1", "bundle_id": BUNDLE_ID, "groups": {}, "companies": {"a": {}, "b": {}}},
    )

    with pytest.raises(StaticDataError, match="Entity count mismatch for groups"):
        verify_static_data(bundle, rumbo)
