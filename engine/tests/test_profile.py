"""Profile card: pure rules, synthetic archetypes, as-of reading, determinism and isolation.

The frames are read straight from the CSVs with a small loader, so the card is
tested on its own: clean columns and liquidity facts come from its stand-ins.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from xray_engine import cleaning, io, profile
from xray_engine.contracts import (
    PROFILE_KEYS,
    SIZE_BAND_LABELS,
    SIZE_BANDS,
    IndustryClassification,
    ProfileCard,
)
from xray_engine.industry_classifier import build_company_signals, classify_dataset, classify_tables
from xray_engine.panel import rows_to_frame
from xray_engine.scoring import score_dataset

MONEY = {
    "debt_products": {"granted": "granted_cents", "outstanding": "outstanding_cents"},
    "transactions": {"amount": "amount_cents"},
    "invoices": {"amount": "amount_cents", "pending_amount": "pending_cents"},
    "balances": {"balance": "balance_cents", "granted": "granted_cents"},
}
DATES = {
    "transactions": ["date"],
    "invoices": ["issuance_date", "due_date", "payment_date"],
    "balances": ["date"],
}
PLACEHOLDERS = ("[COMPANY]", "[NUM]", "[PERSON]", "[ACCOUNT]", "[X]", "NOMINA", "TRANSFERENCIA")


def load_tables(folder: Path, last_month: date | None = None) -> SimpleNamespace:
    """The eight CSVs as cached-like frames: cents, dates, booked rows only."""
    frames: dict[str, object] = {}
    for name in io.TABLE_NAMES:
        raw = (Path(folder) / f"{name}.csv").read_bytes().replace(b"\x00", b"")
        frame = pl.read_csv(raw, schema_overrides=io.SCHEMAS[name])
        for source, target in MONEY.get(name, {}).items():
            cents = (pl.col(source) * 100).round().cast(pl.Int64).alias(target)
            frame = frame.with_columns(cents).drop(source)
        for column in DATES.get(name, []):
            frame = frame.with_columns(pl.col(column).str.slice(0, 10).str.to_date(strict=False))
        frames[name] = frame
    booked = pl.col("status").fill_null("booked") != "pending"
    frames["transactions"] = (
        frames["transactions"].filter(booked)
        .with_columns(pl.col("category").fill_null("-"), pl.col("date").dt.truncate("1mo").alias("month"))
        .select(list(io.CACHE_SCHEMAS["transactions"]))
        .sort("transaction_id")
    )
    if last_month is not None:
        frames["window"] = SimpleNamespace(last_month=last_month)
    return SimpleNamespace(**frames, dataset_hash="test")


def by_key(card: ProfileCard) -> dict[str, object]:
    return {item.key: item for item in card.attributes}


@pytest.fixture(scope="module")
def tables(synthetic) -> SimpleNamespace:
    return load_tables(synthetic.path)


@pytest.fixture(scope="module")
def cards(tables, params) -> dict[str, ProfileCard]:
    return profile.build_profiles(tables, None, params)


# --------------------------------------------------------------------------
# pure rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "code"),
    [("ES", "ES"), ("es", "ES"), ("ESPAÑA", "ES"), ("España ", "ES"), ("Espanya", "ES"), ("Spain", "ES"),
     ("Portugal", "PT"), ("Italia", "IT"), ("Alemania", "DE"), ("Malaysia", "MY"), ("", None),
     (None, None), ("Atlantis", None)],
)
def test_declared_country_is_normalised(declared, code) -> None:
    assert profile.normalise_country(declared) == code


@pytest.mark.parametrize(
    ("bank", "country"),
    [("Banco Santander Empresas", "ES"), ("Caixabank", "ES"), ("BBVA Net Cash Empresas", "ES"),
     ("BANCO SANTANDER TOTTA SA", "PT"), ("Santander (Corporate UK)", "GB"), ("BANCO BPI SA", "PT"),
     ("BBVA Empresas Peru Empresas", "PE"), ("Banco Sabadell Miami", "US"), ("Commerzbank AG", "DE"),
     ("UniCredit eBanking Global by HypoVereinsbank - UniCredit Bank AG", "DE"),
     ("Intesa Sanpaolo", "IT"), ("BNP Paribas - Fortis Corporate", "BE"), ("BNP Paribas", "FR"),
     ("Crédit Agricole Cariparma Spa - Business", "IT"), ("ABN AMRO Bank N.V.", "NL"),
     # global banks, payment institutions and unlinked products say nothing about the country
     ("Other (customer-defined)", None), ("Revolut", None), ("Paypal", None), ("Banca March", None),
     ("Deutsche Bank (ES) - Empresas", None), ("HSBC Corporate GLOBAL", None), ("", None), (None, None)],
)
def test_bank_names_point_to_a_country(bank, country) -> None:
    assert profile.bank_country(bank) == country


def test_country_falls_back_from_master_data_to_language_to_banks() -> None:
    spanish = ["Banco Santander Empresas", "Caixabank"]
    assert profile.infer_country("Portugal", {"es": 500}, spanish)[::2] == ("PT", 1.0)  # declared wins
    code, evidence, coverage = profile.infer_country(None, {"es": 5, "pt": 30, "de": 0}, spanish)
    assert (code, coverage) == ("PT", 30 / 35) and "idioma" in evidence
    # too few markers, or no dominant language: the banks decide
    assert profile.infer_country("", {"pt": 9}, spanish)[0] == "ES"
    assert profile.infer_country("", {"es": 10, "pt": 10, "de": 10}, spanish)[0] == "ES"
    code, evidence, coverage = profile.infer_country(None, None, ["BBVA", "Revolut", "Paypal", "Stripe"])
    assert (code, coverage) == ("ES", 0.25) and "bancos" in evidence  # neutral names only lower the coverage
    assert profile.infer_country(None, {}, ["BBVA", "Commerzbank AG"])[0] is None  # a tie is not a country
    assert profile.infer_country(None, {"es": 20, "nl": 20}, ["Revolut"]) == (
        None, "Sin país declarado, sin idioma dominante en las narrativas y sin banco local claro.", 0.0,
    )
    assert profile.infer_country("Atlantis", None, [])[0] is None


@pytest.mark.parametrize(
    ("erp", "expected"),
    [("netsuite", ("netsuite", "T1")), ("fo", ("fo", "T1")), ("r3", ("r3", "T1")),
     ("businessCentral", ("businessCentral", "T2")), ("sage200", ("sage200", "T2")),
     ("a3", ("a3", "T3")), ("holded", ("holded", "T3")),
     ("Microsoft Business Central", ("businessCentral", "T2")), ("SAP Business One", ("businessOne", "T2")),
     ("Microsoft Dynamics - AX 2012", ("dynamicsAx", "T1")), ("Microsoft Dynamics - F&O", ("fo", "T1")),
     ("SAP R3 / S4", ("r3", "T1")), ("Infor M3 ", ("m3Rosetta", "T1")), ("A3 ERP", ("a3", "T3")),
     ("Sage 50", ("sage50", "T3")), ("Desarrollo propio", ("Desarrollo propio", "OTHER")),
     ("", (None, "NONE")), (None, (None, "NONE"))],
)
def test_erp_names_map_to_a_tier(erp, expected) -> None:
    assert profile.erp_tier(erp) == expected


def test_history_classes_follow_the_eligibility_cuts() -> None:
    assert [profile.history_class(months) for months in (1, 5, 6, 11, 12, 17, 18, 24)] == [
        "D", "D", "C", "C", "B", "B", "A", "A",
    ]


def test_treasury_rules_apply_in_order() -> None:
    base = dict(cash_month_end=100_000.0, n_cash_products=2, headroom=0.0, granted=0.0, drawn=0.0,
                outflow_median_3m=50_000.0, outflow_median_12m=40_000.0, neg_cash_months_6m=0,
                swept_subsidiary=False, invested=0.0)
    code = lambda **changes: profile.treasury_class({**base, **changes})[0]  # noqa: E731
    assert profile.treasury_class(base) == ("adequate", 2.0)
    assert code(swept_subsidiary=True, neg_cash_months_6m=6) == "swept_subsidiary"
    assert code(neg_cash_months_6m=3, granted=10_000.0, drawn=9_900.0) == "overdrawn"
    assert code(granted=10_000.0, drawn=8_100.0) == "line_funded"
    assert code(granted=900.0, drawn=900.0) == "adequate"  # limits below 1 000 EUR are noise
    assert code(cash_month_end=200_000.0, invested=150_000.0) == "cash_rich"
    assert code(cash_month_end=200_000.0) == "comfortable"
    assert code(cash_month_end=20_000.0) == "thin" and code(cash_month_end=10_000.0) == "tight"
    assert code(cash_month_end=10_000.0, headroom=140_000.0) == "comfortable"  # undrawn lines count
    # the 12-month median steps in when the last three months had no outflow
    assert profile.treasury_class({**base, "outflow_median_3m": 0.0}) == ("adequate", 2.5)
    assert code(outflow_median_3m=0.0, outflow_median_12m=None) == "no_flow"
    assert code(outflow_median_3m=None, outflow_median_12m=None, cash_month_end=-5.0) is None
    assert code(cash_month_end=None) is None and code(n_cash_products=0) is None


def test_financing_rules_apply_in_order() -> None:
    debt = lambda kind, drawn, granted=0.0, custom=False: dict(  # noqa: E731
        type=kind, drawn=drawn, granted=granted, custom=custom, known=True)
    assert profile.financing_class([], 0) == ("no_debt", 0.0)
    assert profile.financing_class([], 2)[0] == "no_debt"
    assert profile.financing_class([], 3)[0] == "unconnected_debt"
    assert profile.financing_class([debt("loan", 70.0), debt("loan", 30.0, custom=True)], 0)[0] == "intercompany"
    assert profile.financing_class([debt("lineofcredit", 60.0), debt("loan", 40.0)], 0) == ("working_capital", 0.6)
    assert profile.financing_class([debt("confirming", 20.0), debt("leasing", 80.0)], 0) == ("investment", 0.2)
    assert profile.financing_class([debt("factoring", 40.0), debt("mortgage", 60.0)], 0)[0] == "mixed"
    # nothing drawn: the limits decide
    assert profile.financing_class([debt("lineofcredit", 0.0, 90.0), debt("loan", 0.0, 10.0)], 0)[0] == "working_capital"
    assert profile.headroom_band(0.0, 100.0, 0) == ("none", None)
    assert profile.headroom_band(50.0, None, 1) == (None, None)
    assert [profile.headroom_band(value, 100.0, 1)[0] for value in (20.0, 99.0, 100.0, 299.0, 300.0)] == [
        "no_buffer", "thin", "adequate", "adequate", "ample",
    ]


def test_payment_policy_reads_the_calendar_of_supplier_payments() -> None:
    few = profile.payment_policy({10: 50, 25: 49}, {10: 1.0, 25: 1.0})
    assert few["code"] is None and few["rows"] == 99
    fixed = profile.payment_policy({10: 60, 25: 50, 3: 5, 17: 5}, {10: 600.0, 25: 500.0, 3: 50.0, 17: 50.0})
    assert fixed["code"] == "fixed_days" and fixed["days"] == [10, 25]
    assert fixed["excess"] == pytest.approx(110 / 120 - 2 / 4)
    even = {day: 5 for day in range(1, 29)}
    spread = profile.payment_policy(even, {day: 100.0 for day in even})
    assert spread["code"] == "spread" and spread["excess"] == pytest.approx(0.0)
    late = profile.payment_policy(even, {**{day: 100.0 for day in even}, 28: 5_000.0})
    assert late["code"] == "month_end" and late["month_end_share"] > 0.3


def test_revenue_model_rules_apply_in_order() -> None:
    base = dict(in_rows=240, in_categorised=200, in_pos=0, in_bulk=0, in_ticket=5_000.0, in_months=12,
                gateway_rows=0, gateway_other_rows=0, has_pos_terminal=False)
    code = lambda **changes: profile.revenue_model({**base, **changes})  # noqa: E731
    assert code() == "b2b_standard" and code(in_rows=11) is None
    assert code(in_pos=30) == "pos" and code(in_pos=29) == "b2b_standard"
    assert code(has_pos_terminal=True, in_bulk=100) == "pos"
    assert code(gateway_rows=20, in_ticket=150.0) == "ecommerce"
    assert code(gateway_rows=20, in_ticket=2_500.0) == "b2b_standard"  # large tickets are not a web shop
    assert code(in_bulk=40) == "direct_debit"
    assert code(in_rows=100, in_ticket=25_000.0) == "b2b_project"
    assert code(in_rows=240, in_ticket=25_000.0) == "b2b_standard"  # twenty collections a month


def test_quality_factor_is_the_quality_part_of_the_confidence(params) -> None:
    confidence = params.confidence
    facts = dict(dash_share=0.6, fx_excluded_share=0.2, orphan_product_share=0.05,
                 no_cash_anchor_share=0.5, limit_assumed_constant=True)
    expected = (confidence.quality_dash(0.6) * confidence.quality_fx_excluded(0.2)
                * confidence.quality_orphan(0.05) * confidence.quality_no_cash_anchor(0.5)
                * confidence.limit_assumed_constant_factor)
    assert profile.quality_factor(facts, params) == pytest.approx(expected)
    assert profile.quality_factor({"dash_share": 0.0, "no_cash_anchor_share": None}, params) == 1.0


def test_swept_rule_needs_a_group_and_cash_leaving_it(params) -> None:
    rule = params.liquidity
    base = dict(n_members=3, cash_share_of_group=0.02, zero_balance_account_share=0.0,
                sweep_pairs_out_12m=1, intragroup_net_payer=False)
    swept = lambda **changes: profile.is_swept({**base, **changes}, params)  # noqa: E731
    assert not swept()
    assert swept(zero_balance_account_share=rule.swept_zero_balance_share_min)
    assert not swept(zero_balance_account_share=1.0, sweep_pairs_out_12m=0)  # nothing ever leaves for the group
    assert not swept(zero_balance_account_share=1.0, cash_share_of_group=0.5)
    assert swept(sweep_pairs_out_12m=rule.swept_pairs_min, intragroup_net_payer=True)
    assert not swept(sweep_pairs_out_12m=40, intragroup_net_payer=False)  # funded, not swept
    assert swept(cash_share_of_group=0.005, zero_balance_account_share=0.25)
    assert not swept(n_members=1, zero_balance_account_share=1.0)
    assert not swept(cash_share_of_group=None, zero_balance_account_share=1.0)


# --------------------------------------------------------------------------
# synthetic dataset
# --------------------------------------------------------------------------


def test_every_entity_gets_a_complete_card(cards, synthetic) -> None:
    assert set(cards) == set(synthetic.group_ids) | set(synthetic.company_ids)
    for entity_id, card in cards.items():
        assert card.entity_id == entity_id and card.as_of_month == synthetic.last_month
        assert card.entity_kind == ("group" if entity_id in synthetic.group_ids else "company")
        assert tuple(item.key for item in card.attributes) == PROFILE_KEYS
        assert set(card.context) == {"industry"} and card.context["industry"] is None
        for item in card.attributes:
            assert item.label == profile.PROFILE_LABELS[item.key]
            assert 0.0 <= item.coverage <= 1.0 and (item.value is not None or item.coverage == 0.0)
            assert item.evidence and len(item.evidence) <= 400
            assert item.value is None or (isinstance(item.value, str) and len(item.value) <= 160)
            assert not any(token in item.evidence for token in PLACEHOLDERS)  # never a raw narrative
    company = cards[synthetic.treasury_company_id]
    assert company.group_id == "GROUP_0001" and cards["GROUP_0001"].group_id == "GROUP_0001"


def test_group_roles_of_the_archetypes(cards, synthetic) -> None:
    roles = profile.GROUP_ROLE_LABELS
    value = lambda entity_id: by_key(cards[entity_id])["group_role"].value  # noqa: E731
    assert value(synthetic.treasury_company_id) == roles["treasury_centre"]
    assert value(synthetic.swept_company_id) == roles["swept_subsidiary"]
    assert value(synthetic.no_external_revenue_company_id) == roles["captive"]
    assert value(synthetic.late_member_company_id) == roles["operating_subsidiary"]
    assert value(synthetic.stamped_company_id) == roles["standalone"]
    assert value(synthetic.deteriorating_company_id) == roles["operating_subsidiary"]
    structures = profile.GROUP_STRUCTURE_LABELS
    assert value("GROUP_0001") == structures["centralised_treasury"]
    assert value("GROUP_0002") == structures["single_company"]
    assert value("GROUP_0005") == structures["independent_members"]


def test_swept_subsidiary_is_read_from_structure(tables, cards, synthetic, params) -> None:
    swept = profile.swept_subsidiaries(tables, None, params)
    assert synthetic.swept_company_id in swept
    assert not swept & {synthetic.treasury_company_id, synthetic.late_member_company_id}
    assert synthetic.no_external_revenue_company_id not in swept  # it receives cash, nothing is swept away
    assert all(cards[company_id].group_id == "GROUP_0001" for company_id in swept)  # single-company groups never
    treasury = by_key(cards[synthetic.swept_company_id])["treasury_structure"]
    assert treasury.value == profile.TREASURY_LABELS["swept_subsidiary"]
    own = by_key(cards[synthetic.treasury_company_id])["treasury_structure"]
    assert own.value in {profile.TREASURY_LABELS[code] for code in ("comfortable", "adequate", "thin", "tight")}
    # as of an early month the account is already swept every day
    assert synthetic.swept_company_id in profile.swept_subsidiaries(tables, None, params, month=date(2025, 3, 1))


def test_country_is_declared_then_inferred_from_the_narratives(cards, synthetic) -> None:
    declared = by_key(cards[synthetic.treasury_company_id])["country"]
    assert declared.value == "España (ES)" and declared.coverage == 1.0
    inferred = by_key(cards[synthetic.swept_company_id])["country"]  # blank in companies.csv
    assert inferred.value == "España (ES)" and "idioma" in inferred.evidence and inferred.coverage >= 0.5
    assert by_key(cards["GROUP_0001"])["country"].value == "España (ES)"


def test_erp_size_history_and_financing_of_the_archetypes(cards, synthetic) -> None:
    tiers = profile.ERP_TIER_LABELS
    erp = lambda entity_id: by_key(cards[entity_id])["erp_tier"].value  # noqa: E731
    assert erp(synthetic.treasury_company_id) == f"{tiers['T1']} (netsuite) · con facturas"
    assert erp(synthetic.stamped_company_id) == f"{tiers['T3']} (holded) · con facturas"
    assert erp(synthetic.mid_window_company_id) == f"{tiers['NONE']} · sin facturas"
    assert erp("GROUP_0005") == f"{tiers['T2']} (businessCentral) · con facturas"
    assert erp(synthetic.swept_company_id).endswith("sin facturas")  # the ERP is there, its invoices are not

    for card in cards.values():
        assert by_key(card)["size_band"].value in SIZE_BAND_LABELS.values()
        assert by_key(card)["seasonality"].value is None
    history = lambda entity_id: by_key(cards[entity_id])["history_depth"]  # noqa: E731
    assert history(synthetic.treasury_company_id).value == profile.HISTORY_LABELS["A"]
    assert history(synthetic.late_member_company_id).value == profile.HISTORY_LABELS["A"]  # 19 months
    short = history(synthetic.short_history_company_id)
    assert short.value == profile.HISTORY_LABELS["D"] and short.coverage == pytest.approx(5 / 18, abs=1e-4)
    assert by_key(cards[synthetic.short_history_company_id])["size_band"].coverage == pytest.approx(5 / 12, abs=1e-4)

    financing = lambda entity_id: by_key(cards[entity_id])["financing_profile"]  # noqa: E731
    labels = profile.FINANCING_LABELS
    mixed = financing(synthetic.credit_line_company_id)  # a line drawn at 40 % and a loan
    assert mixed.value.startswith(labels["mixed"]) and "constantes" in mixed.evidence
    assert financing(synthetic.mid_window_company_id).value == (
        f"{labels['investment']} · {profile.HEADROOM_LABELS['none']}"
    )
    assert financing(synthetic.stamped_company_id).value == labels["no_debt"]
    assert financing("GROUP_0006").value == labels["no_debt"]  # a guarantee is not debt


def test_flow_attributes_of_the_archetypes(cards, synthetic) -> None:
    captive = by_key(cards[synthetic.no_external_revenue_company_id])
    assert captive["revenue_model"].value == profile.REVENUE_LABELS["no_external"]
    assert captive["customer_concentration"].value is None  # no collections at all
    swept = by_key(cards[synthetic.swept_company_id])
    assert swept["customer_concentration"].value is None  # no collection names its customer
    group = by_key(cards["GROUP_0001"])
    assert group["customer_concentration"].value == profile.CONCENTRATION_LABELS[False]
    assert 0.2 <= group["customer_concentration"].coverage <= 0.8  # ids and single tokens, not remittances
    assert group["payment_policy"].value == profile.PAYMENT_LABELS["spread"]  # random payment days
    assert by_key(cards[synthetic.short_history_company_id])["payment_policy"].value is None
    assert group["revenue_model"].value in {profile.REVENUE_LABELS[code] for code in ("b2b_standard", "b2b_project")}
    weak = by_key(cards[synthetic.deteriorating_company_id])
    assert weak["data_quality"].value in profile.QUALITY_LABELS.values()
    assert weak["treasury_structure"].coverage == pytest.approx(0.5)  # the sentinel account has no anchor


@pytest.mark.parametrize(("whale_months", "concentrated"), [(8, True), (4, False)])
def test_a_recurrent_top_customer_is_flagged(synthetic, params, whale_months, concentrated) -> None:
    tables = load_tables(synthetic.path)
    company = synthetic.treasury_company_id
    account = tables.transactions.filter(pl.col("company_id") == company)["product_id"][0]
    months = [date(2025, 10, 1), date(2025, 11, 1), date(2025, 12, 1)]
    months = (months + [date(2026, month, 1) for month in range(1, 6)])[:whale_months]
    whale = pl.DataFrame(
        {
            "transaction_id": [f"whale-{index}" for index in range(len(months))],
            "company_id": company, "product_id": account, "date": [m.replace(day=15) for m in months],
            "month": months, "amount_cents": 40_000_000, "status": "booked", "accounting_status": None,
            "category": "collection", "description": "TRANSFERENCIA DE COUNTERPARTY_00777 FRA [NUM]",
            "counterparty_id": None,
        },
        schema=tables.transactions.schema,
    )
    tables.transactions = pl.concat([tables.transactions, whale]).sort("transaction_id")
    item = by_key(profile.build_profiles(tables, None, params)[company])["customer_concentration"]
    assert item.value == profile.CONCENTRATION_LABELS[concentrated]
    assert f"COUNTERPARTY_00777 ({whale_months} meses)" in item.evidence  # harvested from the narrative
    assert item.coverage > 0.5  # most of the collections now name their customer


def test_cards_are_deterministic_and_ignore_row_order(synthetic, datasets, params, cards, tmp_path) -> None:
    assert profile.build_profiles(load_tables(synthetic.path), None, params) == cards
    shuffled = datasets.shuffle(synthetic.path, tmp_path / "shuffled", seed=3)
    assert profile.build_profiles(load_tables(shuffled), None, params) == cards


def test_a_group_alone_gets_the_same_cards(datasets, params, tmp_path) -> None:
    full_dir = datasets.make(tmp_path / "full", n_groups=9, seed=7).path
    full = profile.build_profiles(load_tables(full_dir), None, params)
    for groups in (["GROUP_0001"], ["GROUP_0005", "GROUP_0008"]):
        alone_dir = datasets.filter(full_dir, tmp_path / "-".join(groups), groups)
        alone = profile.build_profiles(load_tables(alone_dir), None, params)
        assert alone == {key: card for key, card in full.items() if card.group_id in groups}


@pytest.mark.parametrize("month", [date(2025, 8, 1), date(2026, 2, 1)])
def test_the_card_is_read_as_of_the_last_month(synthetic, datasets, params, tmp_path, month) -> None:
    cut = profile.build_profiles(load_tables(datasets.truncate(synthetic.path, tmp_path / "cut", month)), None, params)
    early = profile.build_profiles(load_tables(synthetic.path, last_month=month), None, params)
    assert {card.as_of_month for card in cut.values()} == {month}
    assert cut == early
    swept = profile.swept_subsidiaries(load_tables(tmp_path / "cut"), None, params)
    assert swept == profile.swept_subsidiaries(load_tables(synthetic.path), None, params, month=month)


def test_industry_is_context_and_nothing_else(tables, cards, synthetic, params) -> None:
    rng = random.Random(5)
    slugs = ["software", "manufacturing", "healthcare"]
    industry = {
        company_id: IndustryClassification(
            entity_id=company_id, industry_slug=(slug := rng.choice(slugs)), industry_label=slug.title(),
            confidence=0.4 if index % 2 else 0.8, source="signal", reason="regla de prueba",
            classifier_version="test", dataset_hash="test",
        )
        for index, company_id in enumerate(synthetic.company_ids)
    }
    labelled = profile.build_profiles(tables, None, params, industry)
    without = lambda card: dataclasses.replace(card, context={})  # noqa: E731
    assert {key: without(card) for key, card in labelled.items()} == {
        key: without(card) for key, card in cards.items()
    }
    first, second = synthetic.company_ids[:2]
    assert labelled[first].context["industry"] == {
        "slug": industry[first].industry_slug, "label": industry[first].industry_label,
        "confidence": 0.8, "reason": "regla de prueba",
    }
    assert labelled[second].context["industry"]["reason"].startswith("Clasificación de baja confianza")
    members = [industry[company_id].industry_slug for company_id in synthetic.companies_by_group["GROUP_0001"]]
    group = labelled["GROUP_0001"].context["industry"]
    assert set(group) == {"slug", "label", "confidence", "reason"}
    assert members.count(group["slug"]) == max(members.count(slug) for slug in slugs)
    assert 0.0 <= group["confidence"] <= 1.0


def test_liquidity_facts_come_from_the_panel_when_there_is_one(
    tables, cards, synthetic, params, panel_rows, datasets
) -> None:
    rng = random.Random(9)
    company, last = synthetic.late_member_company_id, synthetic.last_month
    rows = [
        panel_rows.random(
            rng, entity_kind="company", entity_id=company, group_id="GROUP_0001", month=last,
            size_band="large", months_observed=3, months_in_12m_window=3, swept_subsidiary=True,
            cash_month_end=10.0, n_cash_products=1, cash_share_of_group=0.001, has_invoices=False,
            dash_share=0.95, fx_excluded_share=0.9, orphan_product_share=0.5, no_cash_anchor_share=1.0,
        ),
        panel_rows.random(
            rng, entity_kind="group", entity_id="GROUP_0001", group_id="GROUP_0001", month=last,
            size_band="medium", months_observed=24, months_in_12m_window=12, swept_subsidiary=False,
        ),
    ]
    solo = synthetic.short_history_company_id  # three of its last four closings below zero
    rows += [
        panel_rows.random(
            rng, entity_kind="company", entity_id=solo, group_id=synthetic.short_history_group_id,
            month=datasets.month_add(last, -offset), swept_subsidiary=False, n_cash_products=1,
            cash_month_end=cash, headroom=0.0, granted=0.0, drawn=0.0, outflow_median_3m=1_000.0,
        )
        for offset, cash in enumerate([500.0, -200.0, -300.0, -100.0])
    ]
    with_panel = profile.build_profiles(tables, rows_to_frame(rows), params)
    overdrawn = by_key(with_panel[solo])["treasury_structure"]
    assert overdrawn.value == profile.TREASURY_LABELS["overdrawn"] and "3 de los últimos 6" in overdrawn.evidence
    card = by_key(with_panel[company])
    assert card["size_band"].value == SIZE_BAND_LABELS["large"] and card["size_band"].coverage == 0.25
    assert card["history_depth"].value == profile.HISTORY_LABELS["D"]
    assert card["group_role"].value == profile.GROUP_ROLE_LABELS["swept_subsidiary"]
    assert card["treasury_structure"].value == profile.TREASURY_LABELS["swept_subsidiary"]
    assert card["erp_tier"].value.endswith("sin facturas")
    assert card["data_quality"].value == profile.QUALITY_LABELS["low"]
    assert by_key(with_panel["GROUP_0001"])["size_band"].value == SIZE_BAND_LABELS["medium"]
    # flows are always read from the rows of the entity
    for key in ("customer_concentration", "payment_policy", "revenue_model", "country"):
        assert card[key] == by_key(cards[company])[key]
    # an entity without a panel row has no liquidity facts, and says so
    missing = by_key(with_panel[synthetic.stamped_company_id])
    assert missing["size_band"].value is None and missing["treasury_structure"].value is None


def test_coverage_report_is_the_share_of_cards_with_a_value(cards) -> None:
    report = profile.coverage_report(cards)
    assert list(report) == list(PROFILE_KEYS) and report["seasonality"] == 0.0
    assert report["size_band"] == 1.0 and report["erp_tier"] == 1.0 and 0.0 < report["payment_policy"] < 1.0
    assert profile.coverage_report(cards, "group")["group_role"] == 1.0
    assert profile.coverage_report({}) == {key: 0.0 for key in PROFILE_KEYS}


def test_industry_signals_accept_a_folder_or_loaded_tables(tables, synthetic, same_frames) -> None:
    from_folder = build_company_signals(synthetic.path).sort("entity_id")
    from_tables = build_company_signals(tables).sort("entity_id")
    assert from_folder["entity_id"].to_list() == sorted(synthetic.company_ids)
    # loaded tables hold booked rows only: the company with pending rows is the one that differs
    pending = synthetic.deteriorating_company_id
    same = pl.col("entity_id") != pending
    same_frames(from_folder.filter(same), from_tables.filter(same), keys=["entity_id"])
    assert (from_folder.filter(~same)["tx_total"] - from_tables.filter(~same)["tx_total"]).to_list() == [
        len(synthetic.pending_transaction_ids)
    ]
    classified = classify_tables(tables)
    assert set(classified) == set(synthetic.company_ids)
    assert {item.dataset_hash for item in classified.values()} == {"test"}
    assert len(classify_dataset(synthetic.path)[1]) == len(synthetic.company_ids)


@pytest.mark.xfail(raises=NotImplementedError, strict=False, reason="io and cleaning are stubs")
def test_clean_tables_give_the_same_structure_as_the_stand_ins(synthetic, params, cards, tmp_path) -> None:
    tables = io.load_tables(synthetic.path, tmp_path / "cache")
    clean = cleaning.clean(tables, params)
    from_clean = profile.build_profiles(clean, None, params)
    assert set(from_clean) == set(cards)
    # the stand-ins skip reversals and weekend bridges: a handful of rows move, the structure does not
    stable = ("country", "size_band", "erp_tier", "group_role", "treasury_structure", "history_depth",
              "seasonality", "data_quality")
    for entity_id, card in from_clean.items():
        assert card.as_of_month == synthetic.last_month
        for key in stable:
            assert by_key(card)[key].value == by_key(cards[entity_id])[key].value, (entity_id, key)
    assert profile.swept_subsidiaries(tables, clean, params) == {synthetic.swept_company_id}
    assert profile.swept_subsidiaries(tables, clean.transactions, params) == {synthetic.swept_company_id}
    # the industry signals read either kind of tables; clean invoices get their sign back
    assert set(classify_tables(tables)) == set(synthetic.company_ids)
    issued = build_company_signals(clean).filter(pl.col("entity_id") == synthetic.treasury_company_id)
    assert 0.0 < issued["invoice_issued_ratio"][0] < 1.0


@pytest.mark.xfail(raises=NotImplementedError, strict=False, reason="engine modules are stubs")
def test_cards_of_a_full_run_follow_the_panel(synthetic, params, tmp_path) -> None:
    run = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache", industry_override={})
    assert set(run.profiles) == set(synthetic.group_ids) | set(synthetic.company_ids)
    last = run.panel.filter(pl.col("month") == synthetic.last_month)
    for row in last.to_dicts():
        card = by_key(run.profiles[row["entity_id"]])
        assert row["size_band"] in SIZE_BANDS and card["size_band"].value == SIZE_BAND_LABELS[row["size_band"]]
        assert card["history_depth"].value == profile.HISTORY_LABELS[profile.history_class(row["months_observed"])]
        swept = card["treasury_structure"].value == profile.TREASURY_LABELS["swept_subsidiary"]
        assert not swept or row["swept_subsidiary"]
        if row["swept_subsidiary"] and row["n_cash_products"] and row["cash_month_end"] is not None:
            assert swept


# --------------------------------------------------------------------------
# real dataset (aggregate statistics only)
# --------------------------------------------------------------------------


@pytest.mark.dataset
def test_attribute_coverage_on_the_real_dataset(real_data_dir, params, tmp_path) -> None:
    try:
        raw = io.load_tables(real_data_dir, tmp_path / "cache")
        tables = cleaning.clean(raw, params)
    except NotImplementedError:  # io or cleaning still a stub: the stand-ins read the CSVs
        raw = tables = load_tables(real_data_dir)
    cards = profile.build_profiles(tables, None, params, classify_tables(raw))
    floors = {
        "country": 0.85, "size_band": 0.99, "erp_tier": 0.99, "group_role": 0.99,
        "treasury_structure": 0.90, "financing_profile": 0.99, "history_depth": 0.99,
        "customer_concentration": 0.40, "payment_policy": 0.30, "revenue_model": 0.70,
        "data_quality": 0.95,
    }
    for kind in ("company", "group"):
        report = profile.coverage_report(cards, kind)
        assert report["seasonality"] == 0.0
        assert not {key: report[key] for key, floor in floors.items() if report[key] < floor}, kind
    companies = [card for card in cards.values() if card.entity_kind == "company"]
    swept = sum(
        by_key(card)["group_role"].value == profile.GROUP_ROLE_LABELS["swept_subsidiary"] for card in companies
    )
    assert 0.03 <= swept / len(companies) <= 0.30
    assert all(card.context["industry"] is not None for card in companies)
    assert max(len(item.evidence) for card in cards.values() for item in card.attributes) <= 400
