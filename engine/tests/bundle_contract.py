"""Checks of the static export bundle against ``contracts/xray-export-v1.schema.json``.

``validate`` is a JSON Schema validator restricted to the keywords the contract
uses; an unknown keyword raises, so nothing is skipped in silence. ``check_bundle``
adds the rules a schema cannot express: the integer identity of every
entity-month, bands, aligned arrays, cross-file references and the bundle id.
The ``companies/`` folder may be absent as a whole (reduced bundle).

Stdlib only. As a script: ``python engine/tests/bundle_contract.py <bundle_dir>``.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "xray-export-v1.schema.json"
FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "fixtures" / "bundle" / "v1"
)
BUNDLE_SCHEMA = "xray-export-v1"
PILLAR_KEYS = ("liquidity", "payments", "collections", "activity", "debt")
BAND_KEYS = ("critical", "watch", "stable", "solid")
SINGLE_FILES = {
    "manifest.json": "manifest",
    "portfolio.json": "portfolio",
    "alerts.json": "alerts",
    "receipt.json": "receipt",
}
ENTITY_FOLDERS = {"groups": "group", "companies": "company", "evidence": "evidence"}
WEIGHT_TOL = 1e-3
CONFIDENCE_TOL = 5e-3

_ANNOTATIONS = {"$schema", "$id", "$defs", "title", "description"}
_TYPES = {
    "null": lambda value: value is None,
    "boolean": lambda value: isinstance(value, bool),
    "integer": lambda value: not isinstance(value, bool)
    and (isinstance(value, int) or (isinstance(value, float) and value.is_integer())),
    "number": lambda value: not isinstance(value, bool) and isinstance(value, (int, float)),
    "string": lambda value: isinstance(value, str),
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
}


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _same(left: Any, right: Any) -> bool:
    return left == right and isinstance(left, bool) == isinstance(right, bool)


def validate(
    instance: Any, schema: Mapping[str, Any], root: Mapping[str, Any], where: str = "$"
) -> list[str]:
    """Errors of ``instance`` against ``schema``; ``root`` resolves ``#/$defs`` refs."""
    errors: list[str] = []
    for keyword, rule in schema.items():
        if keyword in _ANNOTATIONS or keyword in ("then", "else", "additionalProperties"):
            continue
        if keyword == "$ref":
            prefix = "#/$defs/"
            if not rule.startswith(prefix):
                raise ValueError(f"unsupported $ref {rule!r}")
            errors += validate(instance, root["$defs"][rule[len(prefix) :]], root, where)
        elif keyword == "type":
            names = [rule] if isinstance(rule, str) else rule
            if not any(_TYPES[name](instance) for name in names):
                errors.append(f"{where}: expected {'|'.join(names)}, got {type(instance).__name__}")
        elif keyword == "const":
            if not _same(instance, rule):
                errors.append(f"{where}: expected {rule!r}, got {instance!r}")
        elif keyword == "enum":
            if not any(_same(instance, option) for option in rule):
                errors.append(f"{where}: {instance!r} not in {rule}")
        elif keyword in ("minimum", "maximum"):
            if _TYPES["number"](instance) and (
                instance < rule if keyword == "minimum" else instance > rule
            ):
                errors.append(f"{where}: {instance} breaks {keyword} {rule}")
        elif keyword in ("minLength", "maxLength"):
            if isinstance(instance, str) and (
                len(instance) < rule if keyword == "minLength" else len(instance) > rule
            ):
                errors.append(f"{where}: length {len(instance)} breaks {keyword} {rule}")
        elif keyword == "pattern":
            if isinstance(instance, str) and re.search(rule, instance) is None:
                errors.append(f"{where}: {instance!r} does not match {rule}")
        elif keyword in ("minItems", "maxItems"):
            if isinstance(instance, list) and (
                len(instance) < rule if keyword == "minItems" else len(instance) > rule
            ):
                errors.append(f"{where}: {len(instance)} items break {keyword} {rule}")
        elif keyword == "items":
            if isinstance(instance, list):
                for index, item in enumerate(instance):
                    errors += validate(item, rule, root, f"{where}[{index}]")
        elif keyword == "required":
            if isinstance(instance, dict):
                errors += [f"{where}: missing {name!r}" for name in rule if name not in instance]
        elif keyword == "properties":
            if isinstance(instance, dict):
                for name, item in rule.items():
                    if name in instance:
                        errors += validate(instance[name], item, root, f"{where}.{name}")
        elif keyword in ("anyOf", "oneOf"):
            matches = sum(1 for option in rule if not validate(instance, option, root, where))
            if matches == 0 or (keyword == "oneOf" and matches != 1):
                errors.append(f"{where}: matches {matches} options of {keyword}")
        elif keyword == "if":
            branch = "then" if not validate(instance, rule, root, where) else "else"
            if branch in schema:
                errors += validate(instance, schema[branch], root, where)
        else:
            raise ValueError(f"unsupported schema keyword {keyword!r} at {where}")
    extra = schema.get("additionalProperties")
    if extra is not None and isinstance(instance, dict):
        for name in instance.keys() - schema.get("properties", {}).keys():
            if extra is False:
                errors.append(f"{where}: unexpected property {name!r}")
            elif extra is not True:
                errors += validate(instance[name], extra, root, f"{where}.{name}")
    return errors


def bundle_id(bundle_dir: Path) -> str:
    """sha256 over every file but the manifest: path bytes then file bytes, sorted by path."""
    digest = hashlib.sha256()
    files = [item for item in bundle_dir.rglob("*") if item.is_file()]
    for path in sorted(files, key=lambda item: item.relative_to(bundle_dir).as_posix()):
        relative = path.relative_to(bundle_dir).as_posix()
        if relative != "manifest.json":
            digest.update(relative.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def identity_gap(entry: Mapping[str, Any]) -> int:
    """base + sum(contrib) - penalty - cap - shown, in tenths; 0 on a valid entity-month."""
    explained = entry["base"] + sum(pillar["contrib"] for pillar in entry["pillars"])
    return explained - entry["penalty"] - entry["cap"]["amount"] - entry["shown"]


def band_of(shown: int, bands: Sequence[Mapping[str, Any]]) -> str:
    return [band["key"] for band in bands if shown >= band["min"]][-1]


def _month_index(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _contiguous(months: Sequence[str]) -> bool:
    indexes = [_month_index(month) for month in months]
    return all(right - left == 1 for left, right in zip(indexes, indexes[1:]))


def check_entity_month(
    entry: Mapping[str, Any], manifest: Mapping[str, Any], where: str
) -> list[str]:
    errors = []
    if any(isinstance(value, float) for value in _integers(entry)):
        errors.append(f"{where}: tenths must be written as integers")
    gap = identity_gap(entry)
    if gap != 0:
        errors.append(f"{where}: base + contributions - penalty - cap misses shown by {gap} tenths")
    if entry["band"] != band_of(entry["shown"], manifest["bands"]):
        errors.append(f"{where}: band {entry['band']} does not follow shown {entry['shown']}")

    pillars = entry["pillars"]
    if [pillar["key"] for pillar in pillars] != list(PILLAR_KEYS):
        errors.append(f"{where}: pillars are not in contract order")
        return errors
    available = [pillar for pillar in pillars if pillar["score"] is not None]
    nominal = {item["key"]: item["weight"] for item in manifest["pillars"]}
    total = sum(nominal[pillar["key"]] for pillar in available)
    for pillar in pillars:
        if pillar["score"] is None:
            if pillar["w_eff"] != 0 or pillar["contrib"] != 0 or not pillar["gates"]:
                errors.append(f"{where}.{pillar['key']}: needs w_eff 0, contrib 0 and a gate")
        elif abs(pillar["w_eff"] - nominal[pillar["key"]] / total) > WEIGHT_TOL:
            errors.append(f"{where}.{pillar['key']}: w_eff is not the renormalised nominal weight")
    branch = "+".join(pillar["key"] for pillar in available) or "none"
    if entry["branch"] != branch:
        errors.append(f"{where}: branch {entry['branch']!r} should be {branch!r}")

    cap = entry["cap"]
    expected_rule = cap["fired"][0] if cap["amount"] > 0 and cap["fired"] else None
    if cap["rule"] != expected_rule or (cap["amount"] > 0 and not cap["fired"]):
        errors.append(f"{where}: cap.rule must be the first fired cap when it binds, else null")
    errors += _check_actions(entry, where)
    conf = entry["conf"]
    if abs(conf["value"] - conf["history"] * conf["coverage"] * conf["quality"]) > CONFIDENCE_TOL:
        errors.append(f"{where}: conf.value is not history * coverage * quality")
    verdict = entry["verdict"]
    if verdict["shock_pending"] != (verdict["nature"] == "shock_pending"):
        errors.append(f"{where}: shock_pending and nature disagree")
    if verdict["available"] == (verdict["reason"] is not None):
        errors.append(f"{where}: verdict.reason is set exactly when the verdict is not available")
    if not verdict["available"] and (verdict["direction"] != "stable" or verdict["nature"]):
        errors.append(f"{where}: a verdict that is not available must be stable without nature")
    return errors


def _check_actions(entry: Mapping[str, Any], where: str) -> list[str]:
    """Optional ``actions`` / ``actions_combined``: uplifts are tenths against ``shown``."""
    errors = []
    actions = entry.get("actions", [])
    combined = entry.get("actions_combined")
    shown = entry["shown"]
    scores = {pillar["key"]: pillar for pillar in entry["pillars"]}
    for action in actions:
        if action["id"].split("-")[0] != action["pillar"]:
            errors.append(f"{where}: action id {action['id']!r} does not start with its pillar")
        if action["new_score_tenths"] - action["uplift_tenths"] != shown:
            errors.append(f"{where}: action {action['id']} uplift is not new_score - shown")
        if scores[action["pillar"]]["score"] is None:
            errors.append(f"{where}: action {action['id']} on an unavailable pillar")
        if action["pillar"] == "liquidity" and "inherited_from_group" in scores["liquidity"]["gates"]:
            errors.append(f"{where}: no liquidity action on an inherited liquidity")
    uplifts = [action["uplift_tenths"] for action in actions]
    if uplifts != sorted(uplifts, reverse=True) or len({a["id"] for a in actions}) != len(actions):
        errors.append(f"{where}: actions must be unique and sorted by uplift")
    if actions and (entry["abstain"] is not None or not entry["feed_live"]):
        errors.append(f"{where}: abstained or stale months carry no actions")
    if combined is not None:
        if combined["new_score"] - combined["uplift"] != shown:
            errors.append(f"{where}: actions_combined.uplift is not new_score - shown")
        if not actions and combined["uplift"] != 0:
            errors.append(f"{where}: combined uplift without actions")
    return errors


def _integers(entry: Mapping[str, Any]) -> list[Any]:
    values = [entry[name] for name in ("shown", "level", "base", "penalty")]
    values.append(entry["cap"]["amount"])
    for pillar in entry["pillars"]:
        values += [pillar["contrib"], pillar["score"]]
    return values


def _check_months(entity: Mapping[str, Any], manifest: Mapping[str, Any], where: str) -> list[str]:
    months = [entry["month"] for entry in entity["months"]]
    errors = []
    if months != sorted(set(months)) or not set(months) <= set(manifest["months"]):
        errors.append(f"{where}: months must be ascending and inside the manifest window")
    if entity["first_month"] != months[0]:
        errors.append(f"{where}: first_month is not the first scored month")
    for entry in entity["months"]:
        errors += check_entity_month(entry, manifest, f"{where}:{entry['month']}")
    for series in entity["series"]:
        if len(series["values"]) != len(months):
            errors.append(f"{where}: series {series['key']} is not aligned with months")
    inherited = "inherited_from_group" in entity["months"][-1]["pillars"][0]["gates"]
    if entity.get("inherits_liquidity", inherited) != inherited:
        errors.append(f"{where}: inherits_liquidity must follow the last liquidity gate")
    return errors


def _project(entity: Mapping[str, Any], axis: Sequence[str], getter: Any) -> list[Any]:
    by_month = {entry["month"]: entry for entry in entity["months"]}
    return [getter(by_month[month]) if month in by_month else None for month in axis]


def _check_alert(
    alert: Mapping[str, Any], entities: Mapping[str, Any], listed: Mapping[str, Any]
) -> list[str]:
    where = f"alert {alert['id']}"
    errors = []
    if alert["id"] != f"{alert['entity_id']}:{alert['month']}:{alert['kind']}":
        errors.append(f"{where}: id is not '<entity_id>:<month>:<kind>'")
    kind, entity = entities.get(alert["entity_id"], (None, None))
    if entity is None and alert["entity_kind"] == "company" and alert["entity_id"] in listed:
        # reduced bundle without company files: only the group file knows the company
        group, item = listed[alert["entity_id"]]
        shown = dict(zip((entry["month"] for entry in group["months"]), item["shown"]))
        if alert["group_id"] != group["id"] or shown.get(alert["month"]) != alert["shown"]:
            errors.append(f"{where}: group_id or shown differ from the group file")
        return errors
    if entity is None or kind != alert["entity_kind"]:
        return [*errors, f"{where}: unknown entity"]
    owner = alert["entity_id"] if kind == "group" else entity["group_id"]
    if alert["group_id"] != owner:
        errors.append(f"{where}: wrong group_id")
    by_month = {entry["month"]: entry for entry in entity["months"]}
    entry = by_month.get(alert["month"])
    if entry is None:
        return [*errors, f"{where}: the entity has no such month"]
    if alert["shown"] != entry["shown"]:
        errors.append(f"{where}: shown differs from the entity-month")
    abstained = entry["abstain"] is not None
    if alert["state"] == "abstained" and not abstained:
        errors.append(f"{where}: state abstained on a month without abstention")
    if abstained and alert["kind"] != "stale_feed" and alert["state"] != "abstained":
        errors.append(f"{where}: an abstained month cannot fire or suppress alerts")
    muted = alert["suppressed_by"]
    if alert["state"] == "abstained" and muted["reason"] != "abstention":
        errors.append(f"{where}: abstained alerts carry reason 'abstention'")
    if muted is not None and muted["reason"] == "perimeter_change":
        until = muted["until"] or alert["month"]
        if not muted["since"] <= alert["month"] <= until:
            errors.append(f"{where}: outside its suppression window")
        if not by_month.get(muted["since"], {}).get("perimeter_changed", False):
            errors.append(f"{where}: no perimeter change on {muted['since']}")
    return errors


def check_bundle(bundle_dir: Path) -> list[str]:
    """Every violation found in the bundle under ``bundle_dir``; empty when it is valid."""
    bundle_dir = Path(bundle_dir)
    schema = load_schema()
    errors: list[str] = []
    loaded: dict[str, Any] = {}

    def load(relative: str, kind: str) -> None:
        path = bundle_dir / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        found = validate(data, schema["$defs"][kind], schema)
        errors.extend(f"{relative}: {item}" for item in found)
        loaded[relative] = data

    for relative, kind in SINGLE_FILES.items():
        load(relative, kind)
    for folder, kind in ENTITY_FOLDERS.items():
        for path in sorted((bundle_dir / folder).glob("*.json")):
            load(f"{folder}/{path.name}", kind)
    known = set(loaded) | {f"{folder}/" for folder in ENTITY_FOLDERS}
    for path in bundle_dir.rglob("*"):
        relative = path.relative_to(bundle_dir).as_posix()
        if path.is_file() and relative not in known:
            errors.append(f"{relative}: not part of the contract")
    if errors:
        return errors

    manifest, portfolio = loaded["manifest.json"], loaded["portfolio.json"]
    alerts, receipt = loaded["alerts.json"]["alerts"], loaded["receipt.json"]
    groups = {data["id"]: data for name, data in loaded.items() if name.startswith("groups/")}
    companies = {data["id"]: data for name, data in loaded.items() if name.startswith("companies/")}
    evidence = {name: data for name, data in loaded.items() if name.startswith("evidence/")}
    entities = {key: ("group", value) for key, value in groups.items()}
    entities |= {key: ("company", value) for key, value in companies.items()}
    axis = manifest["months"]

    for name, data in loaded.items():
        folder, _, file_name = name.partition("/")
        entity_id = data.get("id", data.get("entity_id"))
        if folder in ENTITY_FOLDERS and file_name != f"{entity_id}.json":
            errors.append(f"{name}: the file name is not the entity id")

    # manifest
    if not _contiguous(axis):
        errors.append("manifest.json: months are not ascending and contiguous")
    if [item["key"] for item in manifest["pillars"]] != list(PILLAR_KEYS):
        errors.append("manifest.json: pillars are not in contract order")
    if abs(sum(item["weight"] for item in manifest["pillars"]) - 1.0) > 1e-9:
        errors.append("manifest.json: nominal weights do not sum 1")
    bands = manifest["bands"]
    minimums = [band["min"] for band in bands]
    ordered = [band["key"] for band in bands] == list(BAND_KEYS) and minimums == sorted(minimums)
    if not ordered or minimums[0] != 0:
        errors.append("manifest.json: bands must be critical, watch, stable, solid from 0 upwards")
        return errors
    listed = {item["id"]: (group, item) for group in groups.values() for item in group["companies"]}
    counts = {"groups": len(groups), "companies": len(listed), "alerts": len(alerts)}
    if manifest["counts"] != counts:
        errors.append(f"manifest.json: counts should be {counts}")
    if manifest["bundle_id"] != bundle_id(bundle_dir):
        errors.append("manifest.json: bundle_id does not match the files")

    # entities
    for group_id, group in groups.items():
        where = f"groups/{group_id}.json"
        errors += _check_months(group, manifest, where)
        months = [entry["month"] for entry in group["months"]]
        members = [item["id"] for item in group["companies"]]
        if members != sorted(set(members)):
            errors.append(f"{where}: companies must be unique and sorted by id")
        for item in group["companies"]:
            if len(item["shown"]) != len(months) or len(item["band"]) != len(months):
                errors.append(f"{where}: {item['id']} is not aligned with months")
        # companies/ is either complete or absent (reduced bundle)
        expected = sorted(key for key, item in companies.items() if item["group_id"] == group_id)
        if not companies:
            continue
        if members != expected:
            errors.append(f"{where}: companies should be {expected}")
            continue
        for item in group["companies"]:
            company = companies[item["id"]]
            for name in ("role", "treasury_class", "truth", "inherits_liquidity", "first_month"):
                if item[name] != company[name]:
                    errors.append(f"{where}: {item['id']}.{name} differs from the company file")
            for name in ("shown", "band"):
                if item[name] != _project(company, months, lambda entry, name=name: entry[name]):
                    errors.append(f"{where}: {item['id']}.{name} is not the company projection")
    for company_id, company in companies.items():
        where = f"companies/{company_id}.json"
        errors += _check_months(company, manifest, where)
        if company["group_id"] not in groups:
            errors.append(f"{where}: unknown group {company['group_id']}")
    for name, data in evidence.items():
        kind, entity = entities.get(data["entity_id"], (None, None))
        months = [item["month"] for item in data["months"]]
        if entity is None or kind != data["entity_kind"]:
            errors.append(f"{name}: unknown entity")
        elif months != sorted(set(months)) or not set(months) <= {
            entry["month"] for entry in entity["months"]
        }:
            errors.append(f"{name}: months must be ascending scored months of the entity")
        elif data["group_id"] != (data["entity_id"] if kind == "group" else entity["group_id"]):
            errors.append(f"{name}: wrong group_id")

    # alerts
    if [(item["month"], item["id"]) for item in alerts] != sorted(
        {(item["month"], item["id"]) for item in alerts}
    ):
        errors.append("alerts.json: alerts must be unique and sorted by (month, id)")
    for alert in alerts:
        errors += _check_alert(alert, entities, {} if companies else listed)
    for entity_id, (kind, entity) in entities.items():
        if entity["alerts"] != [item for item in alerts if item["entity_id"] == entity_id]:
            errors.append(f"{entity_id}: alerts differ from alerts.json")

    # portfolio
    if portfolio["months"] != axis:
        errors.append("portfolio.json: months differ from the manifest")
    if [item["id"] for item in portfolio["groups"]] != sorted(groups):
        errors.append("portfolio.json: groups must be every group file, sorted by id")
        return errors
    columns = {
        "shown": lambda entry: entry["shown"],
        "band": lambda entry: entry["band"],
        "direction": lambda entry: entry["verdict"]["direction"],
        "nature": lambda entry: entry["verdict"]["nature"],
        "conf": lambda entry: entry["conf"]["label"],
        "abstained": lambda entry: entry["abstain"] is not None,
        "perimeter_changed": lambda entry: entry["perimeter_changed"],
    }
    for item in portfolio["groups"]:
        group, where = groups[item["id"]], f"portfolio.json:{item['id']}"
        for name, getter in columns.items():
            if item[name] != _project(group, axis, getter):
                errors.append(f"{where}: {name} is not the projection of the group file")
        facts = (len(group["companies"]), group["first_month"])
        if (item["n_companies"], item["first_month"]) != facts:
            errors.append(f"{where}: n_companies or first_month differ from the group file")
        own = [alert for alert in alerts if alert["group_id"] == item["id"]]
        fired = [sum(a["month"] == m and a["state"] == "fired" for a in own) for m in axis]
        muted = [sum(a["month"] == m and a["state"] != "fired" for a in own) for m in axis]
        if item["alerts_fired"] != fired or item["alerts_muted"] != muted:
            errors.append(f"{where}: alert counts differ from alerts.json")

    # receipt
    for name in ("engine_version", "params_hash", "dataset_hash"):
        if receipt[name] != manifest[name]:
            errors.append(f"receipt.json: {name} differs from the manifest")
    weights = {item["name"]: item["weight"] for item in receipt["signals"]}
    for item in manifest["pillars"]:
        if weights.get(item["key"]) != item["weight"]:
            errors.append(f"receipt.json: signal {item['key']} must carry its nominal weight")
    keys = [item["key"] for item in receipt["checks"]]
    if len(keys) != len(set(keys)):
        errors.append("receipt.json: check keys must be unique")
    expected_abstentions = {
        (entity_id, entity["months"][-1]["abstain"]["reason"])
        for entity_id, (kind, entity) in entities.items()
        if entity["months"][-1]["month"] == axis[-1] and entity["months"][-1]["abstain"] is not None
    }
    abstentions = [
        item for item in receipt["abstentions"] if companies or item["entity_kind"] == "group"
    ]
    found = {(item["entity_id"], item["reason"]) for item in abstentions}
    if found != expected_abstentions or any(i["month"] != axis[-1] for i in receipt["abstentions"]):
        errors.append("receipt.json: abstentions must list every entity abstained last month")
    return errors


def main(argv: Sequence[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else FIXTURE_DIR
    errors = check_bundle(target)
    for item in errors:
        print(item)
    print(f"{target}: {'valid' if not errors else f'{len(errors)} errors'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
