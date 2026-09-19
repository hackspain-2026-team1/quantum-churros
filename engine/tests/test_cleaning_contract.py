"""Row-level cleaning on the synthetic dataset: netting, flow classes, rows that only count."""

from __future__ import annotations

import csv
import re
from collections import Counter

import polars as pl
import pytest
from xray_engine import cleaning, io
from xray_engine.contracts import FLOW_CLASSES

pytestmark = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="io and cleaning are stubs"
)


@pytest.fixture(scope="module")
def clean(synthetic, params, tmp_path_factory) -> cleaning.CleanTables:
    tables = io.load_tables(synthetic.path, tmp_path_factory.mktemp("clean-cache"))
    return cleaning.clean(tables, params)


@pytest.fixture(scope="module")
def booked(synthetic) -> dict[str, dict[str, str]]:
    with (synthetic.path / "transactions.csv").open(newline="", encoding="utf-8") as source:
        rows = csv.DictReader(line.replace("\x00", "") for line in source)
        return {row["transaction_id"]: row for row in rows if row["status"] != "pending"}


def test_no_row_is_dropped_and_the_schema_is_frozen(clean, booked, synthetic) -> None:
    frame = clean.transactions
    expected = {**io.CACHE_SCHEMAS["transactions"], **cleaning.CLEAN_TRANSACTION_COLUMNS}
    assert dict(frame.schema) == expected and list(frame.schema) == list(expected)
    assert frame.height == len(booked) and set(frame["transaction_id"]) == set(booked)
    assert frame["transaction_id"].to_list() == sorted(booked)
    assert not set(frame["transaction_id"]) & set(synthetic.pending_transaction_ids)
    assert set(frame["flow_class"].unique()) <= set(FLOW_CLASSES) and frame["flow_class"].null_count() == 0
    nul = frame.filter(pl.col("transaction_id") == synthetic.nul_transaction_id)
    assert "\x00" not in nul["description"][0]


def test_mirror_recipe(clean, synthetic) -> None:
    rows = {row["transaction_id"]: row for row in clean.transactions.to_dicts()}
    netted = {key for key, row in rows.items() if row["mirror_id"] is not None}
    expected = {item for pair in synthetic.mirror_pairs for item in (pair.out_id, pair.in_id)}
    assert netted == expected
    for pair in synthetic.mirror_pairs:
        out_leg, in_leg = rows[pair.out_id], rows[pair.in_id]
        assert out_leg["mirror_scope"] == in_leg["mirror_scope"] == pair.scope
        assert out_leg["flow_class"] == in_leg["flow_class"] == "internal"  # whatever the category says
        if not pair.ambiguous:
            assert out_leg["mirror_id"] == in_leg["mirror_id"] == pair.out_id
    twins = [pair for pair in synthetic.mirror_pairs if pair.ambiguous]
    ids = Counter(rows[item]["mirror_id"] for pair in twins for item in (pair.out_id, pair.in_id))
    assert sorted(ids) == sorted(pair.out_id for pair in twins) and set(ids.values()) == {2}  # 1:1
    for pair in synthetic.mirror_decoys:  # day gap, below 100 EUR, other currency
        for item in (pair.out_id, pair.in_id):
            assert rows[item]["mirror_id"] is None and rows[item]["mirror_scope"] is None, pair.kind
            assert rows[item]["flow_class"] in ("op_in", "op_out"), pair.kind
    for negative_id, positive_id in synthetic.reversal_pairs:
        for item in (negative_id, positive_id):
            assert rows[item]["reversal_id"] == negative_id and rows[item]["mirror_id"] is None
            assert rows[item]["flow_class"] == "internal"
    reversed_rows = {key for key, row in rows.items() if row["reversal_id"] is not None}
    assert reversed_rows == {item for pair in synthetic.reversal_pairs for item in pair}


def test_flow_classes_follow_the_rule_order(clean, booked, synthetic, datasets, params) -> None:
    rows = {row["transaction_id"]: row for row in clean.transactions.to_dicts()}
    classes = Counter()
    for key, source in booked.items():
        row = rows[key]
        netted = row["mirror_id"] is not None or row["reversal_id"] is not None
        expected = datasets.expected_flow_class(
            source["category"], source["description"], datasets.to_cents(source["amount"]), netted, params
        )
        assert row["flow_class"] == expected, (source["category"], source["description"])
        classes[expected] += 1
    assert set(classes) == set(FLOW_CLASSES)  # the dataset reaches every class
    for key, (flow_class, rule_id) in synthetic.dash_expected.items():
        row = rows[key]
        if row["mirror_id"] is not None:
            continue
        assert (row["flow_class"], row["label_rule"]) == (flow_class, rule_id)
        rule = next((item for item in params.dash_rules if item.id == rule_id), None)
        assert row["label"] == (rule.label if rule else "-")
    interest = [row for row in rows.values() if row["category"] == "interest_charge"]
    assert interest and all(row["flow_class"] == "debt_service" for row in interest)
    labelled = [row for row in rows.values() if row["category"] != "-"]
    assert all(row["label"] == row["category"] and row["label_rule"] is None for row in labelled)


def test_rows_without_a_rate_count_but_never_weigh(clean, synthetic) -> None:
    frame = clean.transactions
    foreign = frame.filter(pl.col("product_id") == synthetic.fx_excluded_product_id)
    assert foreign.height > 0 and foreign["fx_excluded"].all() and foreign["fx_rate"].null_count() == foreign.height
    assert not foreign["orphan_product"].any() and set(foreign["flow_class"]) == {"op_in"}
    orphans = frame.filter(pl.col("orphan_product"))
    assert set(orphans["transaction_id"]) == set(synthetic.orphan_transaction_ids)
    assert orphans["fx_excluded"].all() and orphans["currency"].null_count() == orphans.height
    assert orphans["group_id"].null_count() == 0  # the company still places them in a group
    dollars = frame.filter(pl.col("product_id") == synthetic.usd_product_id)
    assert set(dollars["fx_rate"]) == {0.92} and not dollars["fx_excluded"].any()
    euros = frame.filter(pl.col("currency") == "EUR")
    assert set(euros["fx_rate"]) == {1.0}


def test_counterparty_key_harvests_a_single_token(clean, booked) -> None:
    rows = {row["transaction_id"]: row for row in clean.transactions.to_dicts()}
    harvested = 0
    for key, source in booked.items():
        tokens = re.findall(r"COUNTERPARTY_\d+", source["description"])
        expected = source["counterparty_id"] or (tokens[0] if len(tokens) == 1 else None)
        assert rows[key]["counterparty_key"] == expected
        harvested += bool(expected) and not source["counterparty_id"]
    assert harvested > 50
    assert any(len(re.findall(r"COUNTERPARTY_\d+", source["description"])) == 2 for source in booked.values())
