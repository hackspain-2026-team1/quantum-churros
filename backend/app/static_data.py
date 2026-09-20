from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BUNDLE_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StaticDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class StaticDataVerification:
    bundle_id: str
    checked_files: tuple[Path, ...]
    warnings: tuple[str, ...]


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise StaticDataError(f"Missing static data file: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StaticDataError(f"Invalid static data file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StaticDataError(f"Static data file must contain an object: {path}")
    return value


def verify_static_data(bundle_dir: Path, rumbo_dir: Path) -> StaticDataVerification:
    manifest_path = bundle_dir / "manifest.json"
    manifest = _load_object(manifest_path)
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or not BUNDLE_ID_PATTERN.fullmatch(bundle_id):
        raise StaticDataError(f"Invalid bundle_id in {manifest_path}")

    expected = (
        (rumbo_dir / "params.json", "rumbo-params-v1", True),
        (rumbo_dir / "entities.json", "rumbo-entities-v1", True),
        (rumbo_dir / "products" / "index.json", "rumbo-products-index-v1", False),
        (rumbo_dir / "horizons" / "index.json", "rumbo-horizons-index-v1", True),
    )
    checked = [manifest_path]
    warnings: list[str] = []
    for path, schema, bundle_id_required in expected:
        document = _load_object(path)
        checked.append(path)
        if document.get("schema") != schema:
            raise StaticDataError(
                f"Unexpected schema in {path}: {document.get('schema')!r}, expected {schema!r}"
            )
        derived_bundle_id = document.get("bundle_id")
        if derived_bundle_id is None and not bundle_id_required:
            warnings.append(
                f"{path} has no bundle_id; regenerate products with the current generator"
            )
        elif derived_bundle_id != bundle_id:
            raise StaticDataError(
                f"Bundle mismatch in {path}: {derived_bundle_id!r}, expected {bundle_id!r}"
            )

    entities = _load_object(rumbo_dir / "entities.json")
    counts = manifest.get("counts")
    if isinstance(counts, dict):
        for key in ("groups", "companies"):
            expected_count = counts.get(key)
            actual = entities.get(key)
            if isinstance(expected_count, int) and (
                not isinstance(actual, dict) or len(actual) != expected_count
            ):
                raise StaticDataError(
                    f"Entity count mismatch for {key}: {len(actual) if isinstance(actual, dict) else 'missing'}, expected {expected_count}"
                )

    return StaticDataVerification(
        bundle_id=bundle_id,
        checked_files=tuple(checked),
        warnings=tuple(warnings),
    )
