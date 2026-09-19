"""Core profile card: who the entity is, inferred, with evidence and coverage.

Product surface and gates only. Nothing here feeds pillars or the aggregate;
the industry archetype is attached as ``context["industry"]`` and nowhere else.
Every rule is deterministic and uses the rows of the entity (or of its group)
plus ``Params``: a card does not change with the rest of the cohort.

The card is read as of ``window.last_month``: transactions dated after that
month end are ignored (except by the balance back-roll) and windows are the
trailing 12 months. Liquidity facts (cash, headroom, size band, swept flag,
data-quality shares) come from the panel row of that month, so the card and
the score tell the same story; without a panel a simplified back-roll fills
them in. Frames may be ``CleanTables`` or the cached ``io.Tables``: columns
that cleaning has not added yet are derived with simple stand-ins.

``coverage`` is the part of the data an attribute needs that was there: 1 for
declared master data, the share of agreeing rows, months or accounts for an
inferred value, 0 (with ``value`` None) when nothing can be said. Thresholds
follow the design rules of the card and live here because they never reach a
score; only the concentration rule is a frozen parameter.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import polars as pl

from .contracts import (
    PROFILE_KEYS,
    SIZE_BAND_LABELS,
    Anchors,
    IndustryClassification,
    Params,
    ProfileAttribute,
    ProfileCard,
    size_band_of,
)

if TYPE_CHECKING:
    from .cleaning import CleanTables

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

# --------------------------------------------------------------------------
# code tables and value labels
# --------------------------------------------------------------------------

ERP_TIERS: dict[str, str] = {
    "netsuite": "T1", "dynamicsAx": "T1", "sageX3": "T1", "m3Rosetta": "T1", "r3": "T1",
    "sapByd": "T1", "sageIntacct": "T1", "fo": "T1", "oracleCloud": "T1",
    "businessCentral": "T2", "businessOne": "T2", "sage200": "T2", "navision": "T2",
    "etendo": "T2", "libra": "T2", "ekon": "T2", "datev": "T2",
    "a3": "T3", "distritoK": "T3", "holded": "T3", "sage50": "T3", "odoo": "T3",
}
# group-level names, matched on lower-case alphanumerics
_ERP_ALIASES: tuple[tuple[str, str], ...] = (
    ("businesscentral", "businessCentral"), ("businessone", "businessOne"),
    ("navision", "navision"), ("netsuite", "netsuite"), ("sagex3", "sageX3"),
    ("sage200", "sage200"), ("sage50", "sage50"), ("intacct", "sageIntacct"),
    ("a3erp", "a3"), ("dynamicsax", "dynamicsAx"), ("dynamicsfo", "fo"), ("sapr3", "r3"),
    ("bydesign", "sapByd"), ("holded", "holded"), ("libra", "libra"), ("inform3", "m3Rosetta"),
    ("movex", "m3Rosetta"), ("etendo", "etendo"), ("oraclecloud", "oracleCloud"),
    ("odoo", "odoo"), ("distritok", "distritoK"), ("ekon", "ekon"), ("datev", "datev"),
)
ERP_TIER_LABELS: dict[str, str] = {
    "T1": "ERP corporativo",
    "T2": "ERP de gama media",
    "T3": "ERP de pyme",
    "OTHER": "ERP propio o no catalogado",
    "NONE": "Sin ERP conectado",
}

_COUNTRY_ALIASES: dict[str, str] = {
    "espana": "ES", "espanya": "ES", "spain": "ES", "portugal": "PT", "italia": "IT",
    "italy": "IT", "alemania": "DE", "germany": "DE", "deutschland": "DE", "francia": "FR",
    "france": "FR", "malaysia": "MY", "malasia": "MY", "holanda": "NL", "netherlands": "NL",
    "belgica": "BE", "belgium": "BE", "reinounido": "GB", "unitedkingdom": "GB",
    "estadosunidos": "US", "unitedstates": "US", "mexico": "MX", "colombia": "CO",
    "chile": "CL", "peru": "PE", "argentina": "AR", "andorra": "AD",
}
COUNTRY_NAMES: dict[str, str] = {
    "ES": "España", "PT": "Portugal", "IT": "Italia", "DE": "Alemania", "FR": "Francia",
    "NL": "Países Bajos", "BE": "Bélgica", "GB": "Reino Unido", "US": "Estados Unidos",
    "AT": "Austria", "SE": "Suecia", "PL": "Polonia", "MY": "Malasia", "DK": "Dinamarca",
    "NO": "Noruega", "CH": "Suiza", "IE": "Irlanda", "GR": "Grecia", "MX": "México",
    "CO": "Colombia", "CL": "Chile", "PE": "Perú", "AR": "Argentina", "BR": "Brasil",
    "CA": "Canadá", "AD": "Andorra", "AE": "Emiratos Árabes Unidos", "VN": "Vietnam",
    "EC": "Ecuador",
}
# narrative markers per language; English is not a country and is left out
LANGUAGE_MARKERS: dict[str, str] = {
    "es": r"(?i)\b(transferencia|n[oó]mina|recibo|impuesto)",
    "pt": r"(?i)\b(pagamento|fatura)",
    "de": r"(?i)([uü]berweisung|lastschrift|gehalt)",
    "fr": r"(?i)\b(virement|pr[eé]l[eè]vement)",
    "it": r"(?i)\b(bonifico|fattura|stipendio)",
    "nl": r"(?i)\b(overboeking|incasso|factuur)",
}
LANGUAGE_COUNTRY: dict[str, str] = {
    "es": "ES", "pt": "PT", "de": "DE", "fr": "FR", "it": "IT", "nl": "NL",
}
LANGUAGE_NAMES: dict[str, str] = {
    "es": "español", "pt": "portugués", "de": "alemán", "fr": "francés", "it": "italiano",
    "nl": "neerlandés",
}
# first match wins; None = global or payment institution, no country signal
BANK_COUNTRY_RULES: tuple[tuple[str, str | None], ...] = (
    ((r"other \(customer|paypal|revolut|wise|stripe|payhawk|embat|banking circle|ebury|payoneer"
      r"|adyen|american express|qonto|unitplus|global$|banca march|\(es\)|deutsche bank empresas"
      r"|^ing$|lloyds commercial eu|hsbc corporate|citibank"), None),
    (r"totta|novo ?banco|millennium|caixa geral|\bbpi\b|portugues|portugal|caixa central de ca", "PT"),
    (r"\buk\b|barclays|lloyds|coutts|royal bank of scotland", "GB"),
    ((r"\(usa\)|miami|santander bank - business|wells fargo|bank of america|^chase|city national"
      r"|silicon valley|\bpnc\b|truist|flagstar|banc of california|coastal community|banesco usa"
      r"|eastern fargo|mercury|brex"), "US"),
    (r"peru", "PE"), (r"chile", "CL"), (r"santander rio|banco galicia", "AR"),
    (r"bogot|davivienda", "CO"), (r"pichincha", "EC"), (r"vietcombank", "VN"), (r"^fab$", "AE"),
    (r"canada|desjardins|\(ca\)", "CA"), (r"denmark", "DK"), (r"^dnb$", "NO"), (r"swedbank", "SE"),
    (r"bank austria|erste bank", "AT"), (r"andbank|morabanc", "AD"),
    (r"alpha bank|eurobank|piraeus|bank of greece", "GR"),
    (r"fortis|kbc|cbc belgium", "BE"), (r"abn ?amro|rabobank", "NL"),
    (r"hypovereinsbank|commerzbank|volksbank|sparkasse|^ssk |lbbw|deutsche bank|^vr |volkswagen", "DE"),
    (r"cariparma|intesa|unicredit|monte dei paschi|banco bpm|bper|banca sella|sondrio|^bnl", "IT"),
    (r"cr[eé]dit|societe generale|bnp paribas|caisse d|banque|ark[eé]a|b\.p grand ouest", "FR"),
    ((r"santander|caixabank|bbva|sabadell|bankinter|abanca|ibercaja|cajamar|ruralvia|kutxa|unicaja"
      r"|globalcaja|eurocaja|\bcaja|caixa|arquia|c\.r\.|evo banco|banco caminos|banca pueyo|renta 4"
      r"|iberia cards|redsys|ing direct"), "ES"),
)

GROUP_ROLE_LABELS: dict[str, str] = {
    "standalone": "Empresa independiente",
    "treasury_centre": "Centro de tesorería del grupo",
    "financing_hub": "Centro de financiación del grupo",
    "swept_subsidiary": "Filial con la caja barrida al grupo",
    "captive": "Filial financiada por el grupo",
    "shell": "Sociedad sin actividad operativa",
    "operating_subsidiary": "Filial operativa",
}
GROUP_STRUCTURE_LABELS: dict[str, str] = {
    "single_company": "Grupo de una sola empresa",
    "centralised_treasury": "Grupo con tesorería centralizada",
    "centralised_financing": "Grupo con financiación centralizada",
    "independent_members": "Grupo de empresas con tesorería propia",
}
TREASURY_LABELS: dict[str, str] = {
    "swept_subsidiary": "Tesorería centralizada en el grupo",
    "overdrawn": "Descubierto recurrente",
    "line_funded": "Financiada con líneas de crédito",
    "cash_rich": "Excedentaria (caja e inversiones)",
    "no_flow": "Caja sin salidas recientes",
    "comfortable": "Holgada (3 meses o más de salidas)",
    "adequate": "Adecuada (1 a 3 meses de salidas)",
    "thin": "Justa (10 días a 1 mes de salidas)",
    "tight": "Ajustada (menos de 10 días de salidas)",
}
FINANCING_LABELS: dict[str, str] = {
    "no_debt": "Sin deuda conectada",
    "unconnected_debt": "Deuda no conectada",
    "intercompany": "Financiada por el grupo o los socios",
    "working_capital": "Deuda de circulante",
    "investment": "Deuda de inversión a largo plazo",
    "mixed": "Deuda mixta",
}
HEADROOM_LABELS: dict[str, str] = {
    "none": "sin líneas de crédito",
    "no_buffer": "líneas sin holgura",
    "thin": "holgura escasa",
    "adequate": "holgura adecuada",
    "ample": "holgura amplia",
}
HISTORY_LABELS: dict[str, str] = {
    "A": "A · 18 meses o más",
    "B": "B · 12 a 17 meses",
    "C": "C · 6 a 11 meses",
    "D": "D · menos de 6 meses",
}
CONCENTRATION_LABELS: dict[bool, str] = {
    True: "Concentrada en un cliente",
    False: "Diversificada",
}
PAYMENT_LABELS: dict[str, str] = {
    "fixed_days": "Paga en días fijos",
    "month_end": "Paga a fin de mes",
    "spread": "Pagos repartidos en el mes",
}
REVENUE_LABELS: dict[str, str] = {
    "pos": "Venta con TPV",
    "ecommerce": "Comercio electrónico (pasarelas de pago)",
    "direct_debit": "Recibos domiciliados",
    "b2b_project": "B2B de proyecto (pocos cobros grandes)",
    "b2b_standard": "B2B estándar",
    "no_external": "Sin cobros de fuera del grupo",
}
QUALITY_LABELS: dict[str, str] = {"high": "Alta", "medium": "Media", "low": "Baja"}
_DEBT_TYPE_NAMES: dict[str, tuple[str, str]] = {
    "loan": ("préstamo", "préstamos"),
    "lineofcredit": ("póliza de crédito", "pólizas de crédito"),
    "confirming": ("línea de confirming", "líneas de confirming"),
    "factoring": ("línea de factoring", "líneas de factoring"),
    "leasing": ("leasing", "leasings"),
    "renting": ("renting", "rentings"),
    "mortgage": ("hipoteca", "hipotecas"),
}

# thresholds of the card
INHERITED_ERP_COVERAGE = 0.7
UNCONNECTED_DEBT_MIN_MONTHS = 3  # months with loan repayments and no debt product
LANGUAGE_MIN_HITS = 10
COUNTRY_MIN_SHARE = 0.5
HISTORY_MIN_MONTHS = {"A": 18, "B": 12, "C": 6}
SHORT_TERM_DEBT_TYPES = ("lineofcredit", "confirming", "factoring")
INTERCOMPANY_MIN_SHARE = 0.30
WORKING_CAPITAL_MIN_SHARE = 0.60
INVESTMENT_MAX_SHORT_SHARE = 0.20
MIN_GRANTED_EUR = 1_000.0
HEADROOM_BANDS = ((0.25, "no_buffer"), (1.0, "thin"), (3.0, "adequate"))  # months of outflow
FINANCING_HUB_MIN_SHARE = 0.80
FINANCING_HUB_MIN_MEMBERS = 3
CENTRE_MIN_PAIR_SHARE = 0.5
OVERDRAWN_MIN_MONTHS = 3
OVERDRAWN_WINDOW_MONTHS = 6
LINE_FUNDED_UTILISATION = 0.80
CASH_RICH_MIN_INVESTED_EUR = 100_000.0
INVESTED_PRODUCT_TYPES = ("investment", "saving")
BUFFER_BANDS = ((3.0, "comfortable"), (1.0, "adequate"), (1 / 3, "thin"))  # months of outflow
PAYMENT_MIN_ROWS = 100
PAYMENT_FIXED_EXCESS = 0.15
PAYMENT_MONTH_END_FROM_DAY = 28
PAYMENT_MONTH_END_SHARE = 0.30
PAYMENT_CATEGORIES = ("payment", "bulk_payment")
REVENUE_MIN_ROWS = 12
POS_MIN_SHARE = 0.15
GATEWAY_MIN_SHARE = 0.05
GATEWAY_MAX_TICKET_EUR = 2_000.0
GATEWAY_MIN_ROWS_PER_MONTH = 10
DIRECT_DEBIT_MIN_SHARE = 0.20
PROJECT_MIN_TICKET_EUR = 20_000.0
PROJECT_MAX_ROWS_PER_MONTH = 15
GATEWAY_PATTERN = (
    r"(?i)stripe|paypal|adyen|redsys|shopify|amazon pay|klarna|sumup|mollie|braintree|\bpayout\b"
)
_TOKEN_PATTERN = r"COUNTERPARTY_\d+"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _month_add(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def _months_between(first: date, last: date) -> int:
    return (last.year - first.year) * 12 + last.month - first.month + 1


_SPANISH_SEPARATORS = str.maketrans(",.", ".,")


def _num(value: float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}".translate(_SPANISH_SEPARATORS)


def _pct(share: float) -> str:
    return f"{_num(share * 100)} %"


def _money(eur: float) -> str:
    if abs(eur) >= 1e6:
        return f"{_num(eur / 1e6, 1)} M€"
    if abs(eur) >= 1e3:
        return f"{_num(eur / 1e3)} k€"
    return f"{_num(eur)} €"


def _plural(count: int, one: str, many: str) -> str:
    return f"{_num(count)} {one if count == 1 else many}"


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def _median(values: Sequence[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _attribute(key: str, value: Any, evidence: str, coverage: float) -> ProfileAttribute:
    covered = 0.0 if value is None else round(min(1.0, max(0.0, coverage)), 4)
    return ProfileAttribute(
        key=key, label=PROFILE_LABELS[key], value=value, evidence=evidence[:400], coverage=covered
    )


# --------------------------------------------------------------------------
# pure rules (codes in, codes out)
# --------------------------------------------------------------------------


def normalise_country(declared: str | None) -> str | None:
    """ISO code of a declared country; None when blank or not recognised."""
    text = (declared or "").strip()
    if not text:
        return None
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return _COUNTRY_ALIASES.get(_fold(text))


def bank_country(bank_name: str | None) -> str | None:
    """Country a bank name points to; None for global and payment institutions."""
    text = (bank_name or "").strip().lower()
    for pattern, country in BANK_COUNTRY_RULES:
        if text and re.search(pattern, text):
            return country
    return None


def erp_tier(erp: str | None) -> tuple[str | None, str]:
    """(canonical ERP name, tier) with tier in T1 | T2 | T3 | OTHER | NONE."""
    text = (erp or "").strip()
    if not text:
        return None, "NONE"
    folded = _fold(text)
    for name, tier in ERP_TIERS.items():
        if folded == name.lower():
            return name, tier
    for token, name in _ERP_ALIASES:
        if token in folded:
            return name, ERP_TIERS[name]
    return text, "OTHER"


def history_class(months_observed: int) -> str:
    for code, minimum in HISTORY_MIN_MONTHS.items():
        if months_observed >= minimum:
            return code
    return "D"


def treasury_class(facts: Mapping[str, Any]) -> tuple[str | None, float | None]:
    """(class, buffer in months of outflow); first rule that applies."""
    cash = facts.get("cash_month_end")
    if cash is None or not facts.get("n_cash_products"):
        return None, None
    outflow = facts.get("outflow_median_3m") or facts.get("outflow_median_12m")
    buffer = (cash + (facts.get("headroom") or 0.0)) / outflow if outflow else None
    granted, drawn = facts.get("granted") or 0.0, facts.get("drawn") or 0.0
    if facts.get("swept_subsidiary"):
        return "swept_subsidiary", buffer
    if (facts.get("neg_cash_months_6m") or 0) >= OVERDRAWN_MIN_MONTHS:
        return "overdrawn", buffer
    if granted > MIN_GRANTED_EUR and drawn / granted > LINE_FUNDED_UTILISATION:
        return "line_funded", buffer
    if buffer is None:
        return ("no_flow" if cash > 0 else None), None
    if (facts.get("invested") or 0.0) > CASH_RICH_MIN_INVESTED_EUR and buffer >= BUFFER_BANDS[0][0]:
        return "cash_rich", buffer
    for minimum, code in BUFFER_BANDS:
        if buffer >= minimum:
            return code, buffer
    return "tight", buffer


def financing_class(debts: Sequence[Mapping[str, Any]], debt_service_months: int) -> tuple[str, float]:
    """(class, short-term share). ``debts``: type, drawn, granted (EUR), custom."""
    if not debts:
        unconnected = debt_service_months >= UNCONNECTED_DEBT_MIN_MONTHS
        return ("unconnected_debt" if unconnected else "no_debt"), 0.0
    use_drawn = any(item["drawn"] > 0 for item in debts)
    weights = [item["drawn"] if use_drawn else item["granted"] for item in debts]
    total = sum(weights)
    if total <= 0:
        return "mixed", 0.0
    custom = sum(w for w, item in zip(weights, debts, strict=True) if item["custom"]) / total
    short = sum(
        w for w, item in zip(weights, debts, strict=True) if item["type"] in SHORT_TERM_DEBT_TYPES
    ) / total
    if custom >= INTERCOMPANY_MIN_SHARE:
        return "intercompany", short
    if short >= WORKING_CAPITAL_MIN_SHARE:
        return "working_capital", short
    if short <= INVESTMENT_MAX_SHORT_SHARE:
        return "investment", short
    return "mixed", short


def headroom_band(headroom: float, outflow: float | None, n_lines: int) -> tuple[str | None, float | None]:
    """(band, undrawn limits in months of outflow)."""
    if not n_lines:
        return "none", None
    if not outflow:
        return None, None
    months = headroom / outflow
    for below, code in HEADROOM_BANDS:
        if months < below:
            return code, months
    return "ample", months


def payment_policy(rows_by_day: Mapping[int, int], value_by_day: Mapping[int, float]) -> dict[str, Any]:
    """Fixed-day excess = share of rows on the two busiest days - 2 / distinct days."""
    rows = sum(rows_by_day.values())
    if rows < PAYMENT_MIN_ROWS:
        return {"code": None, "rows": rows}
    ranked = sorted(rows_by_day.items(), key=lambda item: (-item[1], item[0]))
    top = ranked[:2]
    excess = sum(count for _, count in top) / rows - 2 / len(rows_by_day)
    value = sum(value_by_day.values())
    late = sum(amount for day, amount in value_by_day.items() if day >= PAYMENT_MONTH_END_FROM_DAY)
    month_end_share = late / value if value > 0 else 0.0
    if excess >= PAYMENT_FIXED_EXCESS:
        code = "fixed_days"
    elif month_end_share >= PAYMENT_MONTH_END_SHARE:
        code = "month_end"
    else:
        code = "spread"
    return {
        "code": code, "rows": rows, "excess": excess, "month_end_share": month_end_share,
        "days": sorted(day for day, _ in top),
        "top_share": sum(count for _, count in top) / rows,
    }


def revenue_model(stats: Mapping[str, Any]) -> str | None:
    """First rule that applies; ``stats`` from ``_transaction_stats``."""
    rows = stats.get("in_rows", 0)
    if rows < REVENUE_MIN_ROWS:
        return None
    categorised = stats.get("in_categorised", 0)
    ticket = stats.get("in_ticket")
    per_month = rows / max(1, stats.get("in_months", 1))
    if stats.get("has_pos_terminal") or (
        categorised and stats.get("in_pos", 0) / categorised >= POS_MIN_SHARE
    ):
        return "pos"
    gateway = stats.get("gateway_rows", 0)
    if (
        gateway / (rows + stats.get("gateway_other_rows", 0)) >= GATEWAY_MIN_SHARE
        and ticket is not None and ticket < GATEWAY_MAX_TICKET_EUR
        and per_month >= GATEWAY_MIN_ROWS_PER_MONTH
    ):
        return "ecommerce"
    if categorised and stats.get("in_bulk", 0) / categorised >= DIRECT_DEBIT_MIN_SHARE:
        return "direct_debit"
    if ticket is not None and ticket >= PROJECT_MIN_TICKET_EUR and per_month < PROJECT_MAX_ROWS_PER_MONTH:
        return "b2b_project"
    return "b2b_standard"


def quality_factor(facts: Mapping[str, Any], params: Params) -> float:
    """Same recipe as the quality part of the confidence; a None share counts as 1."""
    confidence = params.confidence
    tables: tuple[tuple[str, Anchors], ...] = (
        ("dash_share", confidence.quality_dash),
        ("fx_excluded_share", confidence.quality_fx_excluded),
        ("orphan_product_share", confidence.quality_orphan),
        ("no_cash_anchor_share", confidence.quality_no_cash_anchor),
    )
    factor = 1.0
    for name, anchors in tables:
        if facts.get(name) is not None:
            factor *= anchors(facts[name])
    if facts.get("limit_assumed_constant"):
        factor *= confidence.limit_assumed_constant_factor
    return factor


def is_swept(facts: Mapping[str, Any], params: Params) -> bool:
    """``LiquidityParams`` swept-subsidiary rule on as-of facts of a company.

    A sweep leaves a trace when its destination is inside the observed group,
    so every branch needs at least one intra-group pair paid by the company in
    the window. The pair branch counts the pairs the company pays
    (``sweep_pairs_out_12m``) and asks for a net payer inside the group: in a
    large group every member holds a small share of the cash, so pairs that
    merely touch the company (shared services, funding received) say nothing.
    """
    rule = params.liquidity
    share = facts.get("cash_share_of_group")
    paid = facts.get("sweep_pairs_out_12m") or 0
    if (facts.get("n_members") or 1) <= 1 or share is None or paid == 0:
        return False
    zero_share = facts.get("zero_balance_account_share") or 0.0
    return (
        (zero_share >= rule.swept_zero_balance_share_min and share <= rule.swept_group_cash_share_max)
        or (paid >= rule.swept_pairs_min and bool(facts.get("intragroup_net_payer"))
            and share <= rule.swept_pairs_cash_share_max)
        or (share <= rule.tiny_cash_share_max and zero_share > 0)
    )


# --------------------------------------------------------------------------
# frames: CleanTables or cached Tables, with stand-ins for missing columns
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Frames:
    companies: pl.DataFrame
    groups: pl.DataFrame
    products: pl.DataFrame
    transactions: pl.DataFrame  # every booked row, clean columns included
    invoices: pl.DataFrame | None
    balances: pl.DataFrame
    last_month: date


def _pick(name: str, *sources: Any) -> Any:
    for source in sources:
        value = None if isinstance(source, pl.DataFrame) else getattr(source, name, None)
        if value is not None:
            return value
    return None


def _union_products(tables: Any, companies: pl.DataFrame) -> pl.DataFrame:
    def part(frame: pl.DataFrame, family: str) -> pl.DataFrame:
        cents = [
            (pl.col(name) if name in frame.columns else pl.lit(None, dtype=pl.Int64)).alias(name)
            for name in ("granted_cents", "outstanding_cents")
        ]
        return frame.select(
            "product_id", "company_id", pl.col("type").alias("product_type"),
            pl.lit(family).alias("product_family"), "bank_name", "service", "currency", *cents,
        )

    union = pl.concat([part(tables.banking_products, "banking"), part(tables.debt_products, "debt")])
    return union.join(companies.select("company_id", "group_id"), on="company_id", how="left").sort(
        "product_id"
    )


def _simple_mirrors(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Stand-in for the mirror netting: intra-group opposite twins, 1:1 by rank, no bridge."""
    rule = params.mirror
    key = ["group_id", "currency", "abs_cents", "date"]
    pool = (
        transactions.filter(
            ~pl.col("fx_excluded")
            & (pl.col("amount_cents").abs() / 100 * pl.col("fx_rate") >= rule.min_amount_eur)
        )
        .select("transaction_id", "company_id", "group_id", "product_id", "currency", "date",
                "month", "amount_cents")
        .with_columns(pl.col("amount_cents").abs().alias("abs_cents"))
        .sort("transaction_id")
    )
    found: list[pl.DataFrame] = []
    gaps = [0] + [sign * gap for gap in range(1, rule.max_day_gap + 1) for sign in (1, -1)]
    for gap in gaps:  # date of the positive leg minus date of the negative leg
        ranked = pl.int_range(pl.len()).over(key).alias("rank")
        negative = pool.filter(pl.col("amount_cents") < 0).with_columns(ranked)
        positive = (
            pool.filter(pl.col("amount_cents") > 0)
            .with_columns(pl.col("date").dt.offset_by(f"{-gap}d"))
            .with_columns(ranked)
        )
        pairs = negative.join(positive, on=[*key, "rank"], suffix="_in").filter(
            (pl.col("product_id") != pl.col("product_id_in")) & (pl.col("month") == pl.col("month_in"))
        )
        pairs = pairs.select(
            "transaction_id", "transaction_id_in",
            pl.when(pl.col("company_id") == pl.col("company_id_in"))
            .then(pl.lit("intra_company")).otherwise(pl.lit("intra_group")).alias("mirror_scope"),
        )
        found.append(pairs)
        used = pl.concat([pairs["transaction_id"], pairs["transaction_id_in"]])
        pool = pool.filter(~pl.col("transaction_id").is_in(used.implode()))
    pairs = pl.concat(found)
    legs = pl.concat([
        pairs.select("transaction_id", pl.col("transaction_id").alias("mirror_id"), "mirror_scope"),
        pairs.select(pl.col("transaction_id_in").alias("transaction_id"),
                     pl.col("transaction_id").alias("mirror_id"), "mirror_scope"),
    ])
    return transactions.join(legs, on="transaction_id", how="left")


def _simple_flow_classes(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Stand-in for ``cleaning.classify_flows`` (same rule order, reversals aside)."""
    flows = params.flows
    amount, category = pl.col("amount_cents"), pl.col("category")
    text = pl.col("description").fill_null("").str.replace_all(r"\s+", " ")
    dash = (category == flows.dash_category) & (amount != 0)
    rule_class = pl.lit(None, dtype=pl.String)
    rule_label = pl.lit(None, dtype=pl.String)
    for rule in reversed(params.dash_rules):
        hit = dash & text.str.contains(f"(?i){rule.pattern}")
        if rule.exclude:
            hit = hit & ~text.str.contains(f"(?i){rule.exclude}")
        if rule.sign != "any":
            hit = hit & ((amount < 0) if rule.sign == "negative" else (amount > 0))
        rule_class = pl.when(hit).then(pl.lit(rule.flow_class)).otherwise(rule_class)
        rule_label = pl.when(hit).then(pl.lit(rule.label)).otherwise(rule_label)
    by_sign = pl.when(amount > 0).then(pl.lit("op_in")).otherwise(pl.lit("op_out"))
    flow_class = (
        pl.when(pl.col("mirror_id").is_not_null() | category.is_in(list(flows.internal_categories)))
        .then(pl.lit("internal"))
        .when(dash).then(pl.coalesce(rule_class, by_sign))
        .when((amount < 0) & category.is_in(list(flows.debt_service_categories)))
        .then(pl.lit("debt_service"))
        .when((amount > 0) & category.is_in(list(flows.op_inflow_categories))).then(pl.lit("op_in"))
        .when((amount < 0) & category.is_in(list(flows.op_outflow_categories))).then(pl.lit("op_out"))
        .when(category.is_in(list(flows.financial_categories))).then(pl.lit("financial"))
        .otherwise(pl.lit("other"))
    )
    tokens = pl.col("description").fill_null("").str.extract_all(_TOKEN_PATTERN).list.unique()
    return transactions.with_columns(
        flow_class.alias("flow_class"),
        pl.when(dash).then(pl.coalesce(rule_label, category)).otherwise(category).alias("label"),
        pl.coalesce(
            pl.col("counterparty_id"),
            pl.when(tokens.list.len() == 1).then(tokens.list.first()),
        ).alias("counterparty_key"),
    )


def _with_clean_columns(
    transactions: pl.DataFrame, products: pl.DataFrame, companies: pl.DataFrame, params: Params
) -> pl.DataFrame:
    frame = transactions
    if "group_id" not in frame.columns:
        frame = frame.join(companies.select("company_id", "group_id"), on="company_id", how="left")
    if "fx_rate" not in frame.columns:
        master = products.select("product_id", "currency", "product_type")
        rates = pl.DataFrame(
            {"currency": list(params.fx.rates), "fx_rate": list(params.fx.rates.values())},
            schema={"currency": pl.String, "fx_rate": pl.Float64},
        )
        frame = (
            frame.drop([name for name in ("currency", "product_type") if name in frame.columns])
            .join(master, on="product_id", how="left")
            .join(rates, on="currency", how="left")
            .with_columns(
                pl.col("fx_rate").is_null().alias("fx_excluded"),
                pl.col("product_type").is_null().alias("orphan_product"),
            )
        )
    if "mirror_scope" not in frame.columns:
        frame = _simple_mirrors(frame, params)
    if not {"flow_class", "label", "counterparty_key"} <= set(frame.columns):
        frame = _simple_flow_classes(frame, params)
    return frame


def _frames(tables: Any, cleaned: Any, params: Params, month: date | None) -> _Frames:
    companies = _pick("companies", cleaned, tables)
    groups = _pick("groups", cleaned, tables)
    products = _pick("products", cleaned, tables)
    if products is None:
        products = _union_products(tables, companies)
    transactions = cleaned if isinstance(cleaned, pl.DataFrame) else _pick("transactions", cleaned, tables)
    balances = _pick("balances", cleaned, tables)
    window = _pick("window", cleaned, tables)
    if month is None and window is not None:
        month = window.last_month
    if month is None:  # no window given: last complete month, sentinel balance rows aside
        usable = balances.filter(pl.col("balance_cents").abs() / 100 < params.flows.sentinel_abs_balance)
        latest = max(transactions["date"].max(), usable["date"].max() or date.min)
        month = latest.replace(day=1) if latest == _month_end(latest) else _month_add(latest.replace(day=1), -1)
    return _Frames(
        companies=companies,
        groups=groups if groups is not None else companies.select("group_id").unique(),
        products=products,
        transactions=_with_clean_columns(transactions, products, companies, params),
        invoices=_pick("invoices", cleaned, tables),
        balances=balances,
        last_month=month,
    )


# --------------------------------------------------------------------------
# aggregates (polars in, plain dicts out)
# --------------------------------------------------------------------------


def _eur_sums(frame: pl.DataFrame, keys: list[str], columns: list[str]) -> pl.DataFrame:
    """Int64 cents per (keys, currency) -> EUR per keys; currencies are added in
    a fixed order, so a total never depends on the rest of the cohort."""
    return (
        frame.sort([*keys, "currency"], nulls_last=True)
        .with_columns([(pl.col(name) * pl.col("fx_rate") / 100.0).alias(name) for name in columns])
        .group_by(keys, maintain_order=True)
        .agg([pl.col(name).sum() for name in columns])
    )


def _transaction_stats(
    asof: pl.DataFrame, by: str, start: date, params: Params
) -> dict[str, dict[str, Any]]:
    """Per entity (``by`` = company_id | group_id): history, data quality, monthly
    flows, revenue and payment habits and the top-customer share, trailing 12 months."""
    flows = params.flows
    stats: dict[str, dict[str, Any]] = defaultdict(dict)
    recent = asof.filter(pl.col("month") >= start)
    value = recent.filter(~pl.col("fx_excluded"))
    fx = pl.col("fx_rate").first()
    cents = pl.col("amount_cents").abs().sum().alias("cents")

    for row in asof.group_by(by).agg(pl.col("month").min().alias("first_month")).to_dicts():
        stats[row[by]]["first_month"] = row["first_month"]
    quality = recent.group_by(by).agg(
        pl.len().alias("rows"),
        (pl.col("category") == flows.dash_category).sum().alias("dash"),
        pl.col("fx_excluded").sum().alias("fx_excluded"),
        pl.col("orphan_product").sum().alias("orphan"),
    )
    for row in quality.to_dicts():
        stats[row[by]].update(
            rows_12m=row["rows"], dash_share=row["dash"] / row["rows"],
            fx_excluded_share=row["fx_excluded"] / row["rows"],
            orphan_product_share=row["orphan"] / row["rows"],
        )

    monthly = value.filter(pl.col("flow_class").is_in(["op_in", "op_out", "debt_service"]))
    monthly = monthly.group_by(by, "month", "flow_class", "currency").agg(cents, fx)
    for row in _eur_sums(monthly, [by, "month", "flow_class"], ["cents"]).to_dicts():
        stats[row[by]].setdefault("monthly", {}).setdefault(row["month"], {})[row["flow_class"]] = row["cents"]

    repaid = value.filter((pl.col("flow_class") == "debt_service") & (pl.col("label") == "debt_repayment"))
    for row in repaid.group_by(by).agg(pl.col("month").n_unique().alias("months")).to_dicts():
        stats[row[by]]["repayment_months"] = row["months"]

    inflow = value.filter(pl.col("flow_class") == "op_in")
    gateway = pl.col("description").fill_null("").str.contains(GATEWAY_PATTERN)
    revenue = inflow.group_by(by).agg(
        pl.len().alias("in_rows"),
        (pl.col("label") != flows.dash_category).sum().alias("in_categorised"),
        (pl.col("label") == "pos_settlement").sum().alias("in_pos"),
        (pl.col("label") == "bulk_collection").sum().alias("in_bulk"),
        (pl.col("amount_cents") * pl.col("fx_rate") / 100.0).median().alias("in_ticket"),
        pl.col("month").n_unique().alias("in_months"),
        gateway.sum().alias("gateway_in"),
    )
    for row in revenue.to_dicts():
        stats[row.pop(by)].update(row)
    # gateway payouts are often classed as internal wallet transfers: count them too
    other = value.filter((pl.col("amount_cents") > 0) & (pl.col("flow_class") != "op_in") & gateway)
    for row in other.group_by(by).agg(pl.len().alias("rows")).to_dicts():
        stats[row[by]]["gateway_other_rows"] = row["rows"]
    for entry in stats.values():
        entry["gateway_rows"] = entry.pop("gateway_in", 0) + entry.get("gateway_other_rows", 0)

    payments = value.filter(
        (pl.col("flow_class") == "op_out") & pl.col("label").is_in(list(PAYMENT_CATEGORIES))
    ).with_columns(pl.col("date").dt.day().cast(pl.Int64).alias("day"))
    payments = payments.group_by(by, "day", "currency").agg(pl.len().alias("rows"), cents, fx)
    rows_by_day = payments.group_by(by, "day").agg(pl.col("rows").sum())
    for row in rows_by_day.to_dicts():
        stats[row[by]].setdefault("pay_rows", {})[row["day"]] = row["rows"]
    for row in _eur_sums(payments, [by, "day"], ["cents"]).to_dicts():
        stats[row[by]].setdefault("pay_value", {})[row["day"]] = row["cents"]

    by_key = inflow.group_by(by, "month", "counterparty_key", "currency").agg(cents, fx)
    by_key = _eur_sums(by_key, [by, "month", "counterparty_key"], ["cents"])
    for row in by_key.sort(by, "month", "counterparty_key", nulls_last=True).to_dicts():
        month = stats[row[by]].setdefault("customers", {}).setdefault(
            row["month"], {"total": 0.0, "resolved": 0.0, "top": None, "top_value": 0.0}
        )
        month["total"] += row["cents"]
        if row["counterparty_key"] is not None:
            month["resolved"] += row["cents"]
            if row["cents"] > month["top_value"]:  # ties keep the smallest key
                month["top"], month["top_value"] = row["counterparty_key"], row["cents"]
    return stats


def _language_hits(asof: pl.DataFrame, company_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    if not company_ids:
        return {}
    text = pl.col("description").fill_null("")
    rows = asof.filter(pl.col("company_id").is_in(list(company_ids)))
    hits = rows.group_by("company_id").agg(
        [text.str.contains(pattern).sum().alias(language) for language, pattern in LANGUAGE_MARKERS.items()]
    )
    return {row.pop("company_id"): row for row in hits.to_dicts()}


def _sweep_pairs(recent: pl.DataFrame) -> list[dict[str, Any]]:
    """Intra-group mirror pairs of the window: group, paying and receiving company, EUR."""
    legs = recent.filter(pl.col("mirror_scope") == "intra_group")
    paid = pl.col("amount_cents") < 0
    pairs = legs.group_by("mirror_id").agg(
        pl.col("group_id").first(),
        pl.col("company_id").filter(paid).first().alias("out_company"),
        pl.col("company_id").filter(~paid).first().alias("in_company"),
        (pl.col("amount_cents").abs() * pl.col("fx_rate") / 100.0).filter(paid).first().alias("eur"),
    )
    return pairs.drop_nulls(["out_company", "in_company"]).sort("mirror_id").to_dicts()


def _anchors(frames: _Frames, params: Params) -> pl.DataFrame:
    """Latest usable balance row per product, with product facts and the limit."""
    flows = params.flows
    rates = pl.DataFrame(
        {"currency": list(params.fx.rates), "fx_rate": list(params.fx.rates.values())},
        schema={"currency": pl.String, "fx_rate": pl.Float64},
    )
    master = frames.products.select(
        "product_id", "group_id", "product_type", "currency",
        pl.col("granted_cents").alias("product_granted_cents"),
    ).join(rates, on="currency", how="left")
    usable = frames.balances.filter(
        pl.col("balance_cents").abs() / 100 < flows.sentinel_abs_balance
    ).sort("product_id", "date")
    latest = usable.group_by("product_id", maintain_order=True).agg(
        pl.col("company_id").last(), pl.col("date").last().alias("anchor_date"),
        pl.col("balance_cents").last(), pl.col("granted_cents").last(),
    )
    return latest.join(master, on="product_id", how="inner").with_columns(
        pl.coalesce("granted_cents", "product_granted_cents").abs().fill_null(0).alias("limit_cents")
    )


def _balances_at(transactions: pl.DataFrame, anchors: pl.DataFrame, ends: Sequence[date]) -> pl.DataFrame:
    """Back-rolled balance per anchored product at every date of ``ends`` (``balance_<i>``)."""
    moves = transactions.select("product_id", "date", "amount_cents").join(
        anchors.select("product_id", "anchor_date"), on="product_id", how="inner"
    )
    day, anchor, amount = pl.col("date"), pl.col("anchor_date"), pl.col("amount_cents")
    shifts = [
        (
            pl.when((day > anchor) & (day <= end)).then(amount).otherwise(0)
            - pl.when((day > end) & (day <= anchor)).then(amount).otherwise(0)
        ).sum().alias(f"shift_{index}")
        for index, end in enumerate(ends)
    ]
    shifted = anchors.join(moves.group_by("product_id").agg(shifts), on="product_id", how="left")
    return shifted.with_columns(
        [
            (pl.col("balance_cents") + pl.col(f"shift_{index}").fill_null(0)).alias(f"balance_{index}")
            for index in range(len(ends))
        ]
    )


def _zero_balance_accounts(
    asof: pl.DataFrame, cash: pl.DataFrame, start: date, end: date, params: Params
) -> set[str]:
    """Active cash accounts that sit at zero on most days of the window.

    Scale of an account = the larger p95 of its daily |balance| and of its
    daily turnover, so an account swept to the cent still has a scale.
    """
    rule = params.liquidity
    window = asof.filter(pl.col("product_id").is_in(cash["product_id"].implode()))
    first_seen = window.group_by("product_id").agg(pl.col("month").min().alias("first_seen"))
    daily = window.filter(pl.col("date") >= start).group_by("product_id", "date").agg(
        pl.col("amount_cents").sum().alias("net"),
        pl.col("amount_cents").abs().sum().alias("turnover"),
    )
    active = daily.select("product_id").unique()
    grid = (
        cash.select("product_id", pl.col("balance_0").alias("closing"))
        .join(active, on="product_id", how="inner")
        .join(first_seen, on="product_id", how="left")
        .with_columns(pl.max_horizontal(pl.col("first_seen"), pl.lit(start)).alias("from"))
        .with_columns(pl.date_ranges(pl.col("from"), pl.lit(end), interval="1d", closed="both").alias("date"))
        .explode("date", empty_as_null=False)
        .join(daily, on=["product_id", "date"], how="left")
        .with_columns(pl.col("net").fill_null(0), pl.col("turnover").fill_null(0))
        .sort("product_id", "date")
    )
    later = pl.col("net").cum_sum(reverse=True).over("product_id") - pl.col("net")
    grid = grid.with_columns((pl.col("closing") - later).abs().alias("level"))
    scale = pl.max_horizontal(
        pl.col("level").quantile(0.95),
        pl.col("turnover").filter(pl.col("turnover") > 0).quantile(0.95).fill_null(0),
    )
    verdict = grid.group_by("product_id").agg(
        (pl.col("level") <= rule.zero_balance_relative * scale).mean().alias("share")
    )
    flagged = verdict.filter(pl.col("share") >= rule.zero_balance_days_share)
    return set(flagged["product_id"].to_list())


def _liquidity_facts(
    frames: _Frames, asof: pl.DataFrame, params: Params
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Simplified back-roll behind the card when no panel is given: (company, group) facts."""
    flows = params.flows
    last = frames.last_month
    months = [_month_add(last, -offset) for offset in range(OVERDRAWN_WINDOW_MONTHS)]
    rolled = _balances_at(frames.transactions, _anchors(frames, params), [_month_end(m) for m in months])
    company_first = dict(asof.group_by("company_id").agg(pl.col("month").min()).iter_rows())
    product_first = dict(asof.group_by("product_id").agg(pl.col("month").min()).iter_rows())
    group_of = dict(frames.companies.select("company_id", "group_id").iter_rows())

    cash = rolled.filter(pl.col("product_type").is_in(list(flows.cash_product_types)))
    start = _month_add(last, -11)
    zero = _zero_balance_accounts(asof, cash, start, _month_end(last), params)
    active = set(asof.filter(pl.col("month") >= start)["product_id"].unique().to_list())

    company: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(float))
    series: dict[str, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for row in rolled.sort("product_id").to_dicts():
        owner, product = row["company_id"], row["product_id"]
        joined = product_first.get(product) or company_first.get(owner)
        if joined is None or row["fx_rate"] is None:
            continue
        facts = company[owner]
        if row["product_type"] in flows.cash_product_types:
            facts["n_cash_products"] += 1
            facts["active_cash"] += product in active
            facts["zero_cash"] += product in zero
            for index, month in enumerate(months):
                if joined <= month:
                    series[owner][index][row["currency"]] += row[f"balance_{index}"]
        elif row["product_type"] in flows.revolving_product_types and joined <= last:
            limit = row["limit_cents"] / 100 * row["fx_rate"]
            drawn = max(0, -row["balance_0"]) / 100 * row["fx_rate"]
            facts["n_credit_lines"] += 1
            facts["granted"] += limit
            facts["drawn"] += drawn
            facts["headroom"] += max(0.0, limit - drawn)
    for owner, by_index in series.items():
        closing = {
            index: sum(cents * params.fx.rates[currency] for currency, cents in sorted(values.items())) / 100
            for index, values in by_index.items()
        }
        company[owner]["cash_by_month"] = closing
        if 0 in closing:
            company[owner]["cash_month_end"] = closing[0]

    # cash accounts with booked rows and no usable anchor
    anchored = set(rolled["product_id"].to_list())
    booked = asof.filter(pl.col("product_type").is_in(list(flows.cash_product_types)))
    for owner, product in booked.select("company_id", "product_id").unique().sort("product_id").iter_rows():
        company[owner]["booked_cash"] += 1
        company[owner]["unanchored_cash"] += product not in anchored

    group: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(float))
    for owner in sorted(company):
        facts, pooled = company[owner], group[group_of.get(owner, owner)]
        for name in ("n_cash_products", "n_credit_lines", "granted", "drawn", "headroom",
                     "booked_cash", "unanchored_cash"):
            pooled[name] += facts.get(name, 0)
        for index, amount in facts.get("cash_by_month", {}).items():
            pooled.setdefault("cash_by_month", {})
            pooled["cash_by_month"][index] = pooled["cash_by_month"].get(index, 0.0) + amount
    for facts in [*company.values(), *group.values()]:
        closing = facts.pop("cash_by_month", {})
        facts["cash_month_end"] = closing.get(0)
        facts["neg_cash_months_6m"] = sum(1 for amount in closing.values() if amount < 0)
        facts["limit_assumed_constant"] = facts.get("granted", 0) > 0
        booked_cash = facts.pop("booked_cash", 0)
        unanchored = facts.pop("unanchored_cash", 0)
        facts["no_cash_anchor_share"] = unanchored / booked_cash if booked_cash else None
    for owner, facts in company.items():
        active_cash, zero_cash = facts.pop("active_cash", 0), facts.pop("zero_cash", 0)
        facts["zero_balance_account_share"] = zero_cash / active_cash if active_cash else None
        pooled = group[group_of.get(owner, owner)].get("cash_month_end")
        own = facts.get("cash_month_end")
        facts["cash_share_of_group"] = own / pooled if own is not None and pooled and pooled > 0 else None
    return {key: dict(value) for key, value in company.items()}, {
        key: dict(value) for key, value in group.items()
    }


def _flow_facts(stats: Mapping[str, Any], last: date, params: Params) -> dict[str, Any]:
    """History, size band and outflow medians from the monthly flows of one entity."""
    from .panel import winsorised_sum  # local import: panel may import this module

    first = stats.get("first_month")
    if first is None:
        return {"months_observed": 0}
    observed = [m for m in (_month_add(last, -offset) for offset in range(11, -1, -1)) if m >= first]
    monthly = stats.get("monthly", {})
    inflow = [monthly.get(m, {}).get("op_in", 0.0) for m in observed]
    outflow = [
        monthly.get(m, {}).get("op_out", 0.0) + monthly.get(m, {}).get("debt_service", 0.0)
        for m in observed
    ]
    inflow_w = winsorised_sum(inflow, params.robust.monthly_winsor_multiple)
    facts: dict[str, Any] = {
        "months_observed": _months_between(first, last),
        "months_in_12m_window": len(observed),
        "op_in_sum_12m_w": inflow_w,
        "debt_service_sum_12m_w": sum(monthly.get(m, {}).get("debt_service", 0.0) for m in observed),
        "outflow_median_3m": _median(outflow[-params.liquidity.outflow_window_months:]),
        "outflow_median_12m": _median(outflow),
        "size_band": None,
    }
    if observed:
        facts["size_band"] = size_band_of(
            inflow_w * 12 / len(observed), params.size_bands.upper_bounds_eur
        )
    return facts


_PANEL_FACTS = (
    "months_observed", "n_members", "size_band", "op_in_sum_12m_w", "months_in_12m_window",
    "cash_month_end", "headroom", "granted", "drawn", "n_cash_products", "n_credit_lines",
    "no_cash_anchor_share", "limit_assumed_constant", "swept_subsidiary", "cash_share_of_group",
    "zero_balance_account_share", "sweep_pairs_12m", "outflow_median_3m", "outflow_median_12m",
    "debt_service_sum_12m_w", "has_invoices", "dash_share", "fx_excluded_share",
    "orphan_product_share",
)


def _panel_facts(panel: pl.DataFrame, last: date) -> dict[tuple[str, str], dict[str, Any]]:
    """Facts of the last month per (entity_kind, entity_id), from ``PANEL_COLUMNS`` rows."""
    first = _month_add(last, -(OVERDRAWN_WINDOW_MONTHS - 1))
    rows = panel.filter(pl.col("month").is_between(first, last)).sort("entity_kind", "entity_id", "month")
    facts: dict[tuple[str, str], dict[str, Any]] = {}
    negative: Counter[tuple[str, str]] = Counter()
    for row in rows.to_dicts():
        key = (row["entity_kind"], row["entity_id"])
        negative[key] += row["cash_month_end"] is not None and row["cash_month_end"] < 0
        if row["month"] == last:
            facts[key] = {name: row[name] for name in _PANEL_FACTS}
    for key, values in facts.items():
        values["neg_cash_months_6m"] = negative[key]
    return facts


# --------------------------------------------------------------------------
# attributes
# --------------------------------------------------------------------------


def _dominant(counts: Mapping[str, int]) -> tuple[str, int] | None:
    """Key holding at least ``COUNTRY_MIN_SHARE`` of the counts, alone at the top."""
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    total = sum(counts.values())
    if not total or ranked[0][1] / total < COUNTRY_MIN_SHARE:
        return None
    if len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
        return None
    return ranked[0]


def infer_country(
    declared: str | None, hits: Mapping[str, int] | None, banks: Sequence[str | None]
) -> tuple[str | None, str, float]:
    """(ISO code, evidence, coverage): declared, then narrative language, then banks.

    ``hits`` counts the rows with a marker of each language; ``banks`` lists
    the bank name of every banking product.
    """
    code = normalise_country(declared)
    if code is not None:
        return code, "País declarado en el maestro de empresas.", 1.0
    total = sum((hits or {}).values())
    language = _dominant(hits) if hits and total >= LANGUAGE_MIN_HITS else None
    if language is not None:
        return LANGUAGE_COUNTRY[language[0]], (
            f"Sin país declarado: inferido del idioma de las narrativas bancarias "
            f"({_pct(language[1] / total)} de {_num(total)} movimientos con marcador están en "
            f"{LANGUAGE_NAMES[language[0]]})."
        ), language[1] / total
    # global banks and payment institutions carry no signal: they only lower the coverage
    located = _dominant(Counter(country for country in map(bank_country, banks) if country))
    if located is not None:
        country, count = located
        return country, (
            f"Sin país declarado ni idioma dominante: {_num(count)} de "
            f"{_plural(len(banks), 'cuenta bancaria está', 'cuentas bancarias están')} en bancos de "
            f"{COUNTRY_NAMES.get(country, country)}."
        ), count / len(banks)
    return None, "Sin país declarado, sin idioma dominante en las narrativas y sin banco local claro.", 0.0


def _country_value(code: str) -> str:
    return f"{COUNTRY_NAMES[code]} ({code})" if code in COUNTRY_NAMES else code


def _group_country(members: Sequence[tuple[str | None, float]]) -> ProfileAttribute:
    known = [code for code, _ in members if code]
    if not known:
        return _attribute("country", None, "Ninguna empresa del grupo tiene un país inferible.", 0.0)
    counts = Counter(known)
    code, count = min(counts.items(), key=lambda item: (-item[1], item[0]))
    value = _country_value(code)
    if len(counts) > 1:
        value = f"{value} · multinacional"
    others = ", ".join(sorted(set(counts) - {code}))
    country = COUNTRY_NAMES.get(code, code)
    evidence = f"{_num(count)} de {_plural(len(members), 'empresa', 'empresas')} en {country}"
    evidence += f"; también presente en {others}." if others else "."
    coverage = sum(share for item, share in members if item) / len(members)
    return _attribute("country", value, evidence, coverage)


def _size_attribute(facts: Mapping[str, Any]) -> ProfileAttribute:
    band, months = facts.get("size_band"), facts.get("months_in_12m_window") or 0
    if band is None or not months:
        return _attribute("size_band", None, "Sin meses observados para anualizar los cobros.", 0.0)
    annual = (facts.get("op_in_sum_12m_w") or 0.0) * 12 / months
    evidence = (
        f"Cobros operativos anualizados de {_money(annual)} "
        f"({_plural(months, 'mes observado', 'meses observados')} de los últimos 12, sin movimientos internos)."
    )
    return _attribute("size_band", SIZE_BAND_LABELS[band], evidence, months / 12)


def _erp_attribute(own: str | None, inherited: str | None, has_invoices: bool, scope: str) -> ProfileAttribute:
    name, tier = erp_tier(own)
    coverage = 1.0
    source = f"ERP declarado por {scope}"
    if tier == "NONE" and inherited:
        name, tier = erp_tier(inherited)
        coverage, source = INHERITED_ERP_COVERAGE, "ERP heredado del grupo"
    invoices = "con facturas" if has_invoices else "sin facturas"
    if tier == "NONE":
        value = f"{ERP_TIER_LABELS[tier]} · {invoices}"
        evidence = (
            "Llegan facturas sin un ERP declarado: el origen no está identificado."
            if has_invoices else "No hay ERP declarado ni facturas: solo datos bancarios."
        )
        return _attribute("erp_tier", value, evidence, 0.5 if has_invoices else 1.0)
    value = f"{ERP_TIER_LABELS[tier]} ({name}) · {invoices}"
    evidence = f"{source}: {name}. " + (
        "El feed de facturas está conectado." if has_invoices
        else "No llega ninguna factura: los pilares de pagos y cobros no se pueden medir."
    )
    return _attribute("erp_tier", value, evidence, coverage)


def _history_attribute(months: int, first: date | None, params: Params) -> ProfileAttribute:
    if not months or first is None:
        return _attribute("history_depth", None, "Sin movimientos bancarios contabilizados.", 0.0)
    code = history_class(months)
    minimum = params.abstention.min_months_observed
    trajectory = params.trajectory.min_scored_months
    if months < minimum:
        reach = f"el motor se abstiene hasta tener {minimum} meses"
    elif months < trajectory:
        reach = f"nivel sin trayectoria hasta tener {trajectory} meses"
    else:
        reach = "nivel y trayectoria disponibles"
    evidence = f"{_plural(months, 'mes observado', 'meses observados')} desde {first:%Y-%m}: {reach}."
    return _attribute("history_depth", HISTORY_LABELS[code], evidence, months / HISTORY_MIN_MONTHS["A"])


def _seasonality_attribute() -> ProfileAttribute:
    return _attribute(
        "seasonality", None,
        "Con dos años de historia el mes del año no se distingue del ruido: el motor no "
        "desestacionaliza ni publica un patrón estacional.", 0.0,
    )


def _concentration_attribute(stats: Mapping[str, Any], last: date, params: Params) -> ProfileAttribute:
    rule = params.profile
    window = [_month_add(last, -offset) for offset in range(rule.concentration_window_months)]
    months = [stats.get("customers", {}).get(month) for month in window]
    months = [month for month in months if month and month["total"] > 0]
    total = sum(month["total"] for month in months)
    if total <= 0:
        return _attribute("customer_concentration", None,
                          "Sin cobros operativos en los últimos 12 meses.", 0.0)
    flagged = [m for m in months if m["top_value"] / m["total"] >= rule.concentration_top1_share]
    concentrated = len(flagged) >= rule.concentration_min_months
    resolved = sum(month["resolved"] for month in months) / total
    if not concentrated and resolved < rule.concentration_top1_share:
        return _attribute(
            "customer_concentration", None,
            f"Solo el {_pct(resolved)} de los cobros identifica al cliente: por debajo del "
            f"{_pct(rule.concentration_top1_share)} la regla no puede activarse.", 0.0,
        )
    evidence = (
        f"El primer cliente alcanza el {_pct(rule.concentration_top1_share)} de los cobros del mes en "
        f"{_num(len(flagged))} de los últimos {rule.concentration_window_months} meses "
        f"(umbral: {rule.concentration_min_months})."
    )
    if flagged:
        name, count = min(Counter(m["top"] for m in flagged).items(), key=lambda i: (-i[1], i[0]))
        evidence += f" El más repetido es {name} ({_plural(count, 'mes', 'meses')})."
    evidence += f" Cobros con cliente identificado: {_pct(resolved)}."
    return _attribute("customer_concentration", CONCENTRATION_LABELS[concentrated], evidence, resolved)


def _payment_attribute(stats: Mapping[str, Any]) -> ProfileAttribute:
    policy = payment_policy(stats.get("pay_rows", {}), stats.get("pay_value", {}))
    if policy["code"] is None:
        return _attribute(
            "payment_policy", None,
            f"{_plural(policy['rows'], 'pago a proveedores', 'pagos a proveedores')} en 12 meses: "
            f"hacen falta {PAYMENT_MIN_ROWS} para leer un calendario de pago.", 0.0,
        )
    value = PAYMENT_LABELS[policy["code"]]
    if policy["code"] == "fixed_days":
        value += f" (días {policy['days'][0]} y {policy['days'][-1]})" if len(policy["days"]) > 1 else ""
    evidence = (
        f"{_pct(policy['top_share'])} de {_num(policy['rows'])} pagos a proveedores caen en los dos días "
        f"más usados del mes; {_pct(policy['month_end_share'])} del importe se paga del día "
        f"{PAYMENT_MONTH_END_FROM_DAY} en adelante."
    )
    return _attribute("payment_policy", value, evidence, 1.0)


def _revenue_attribute(stats: Mapping[str, Any], captive: bool) -> ProfileAttribute:
    if captive:
        return _attribute(
            "revenue_model", REVENUE_LABELS["no_external"],
            "Todas las entradas de los últimos 12 meses son movimientos internos del grupo.", 1.0,
        )
    code = revenue_model(stats)
    rows = stats.get("in_rows", 0)
    if code is None:
        return _attribute(
            "revenue_model", None,
            f"{_plural(rows, 'cobro operativo', 'cobros operativos')} en 12 meses: hacen falta "
            f"{REVENUE_MIN_ROWS} para leer un modelo de ingreso.", 0.0,
        )
    categorised = stats.get("in_categorised", 0)
    share = (lambda count: _pct(count / categorised) if categorised else "0 %")
    evidence = (
        f"{_num(rows)} cobros en {_plural(stats.get('in_months', 0), 'mes', 'meses')}, ticket mediano "
        f"{_money(stats.get('in_ticket') or 0.0)}; TPV {share(stats.get('in_pos', 0))} y remesas "
        f"{share(stats.get('in_bulk', 0))} de los cobros categorizados; "
        f"{_num(stats.get('gateway_rows', 0))} abonos de pasarelas de pago."
    )
    return _attribute("revenue_model", REVENUE_LABELS[code], evidence, min(1.0, stats.get("in_months", 0) / 12))


def _quality_attribute(facts: Mapping[str, Any], params: Params) -> ProfileAttribute:
    if facts.get("dash_share") is None:
        return _attribute("data_quality", None, "Sin movimientos en los últimos 12 meses.", 0.0)
    factor = quality_factor(facts, params)
    confidence = params.confidence
    code = "high" if factor >= confidence.label_high_min else (
        "medium" if factor >= confidence.label_medium_min else "low"
    )
    evidence = (
        f"Movimientos sin categoría: {_pct(facts['dash_share'])}; en divisas sin tipo de cambio: "
        f"{_pct(facts.get('fx_excluded_share') or 0.0)}; de cuentas fuera del maestro: "
        f"{_pct(facts.get('orphan_product_share') or 0.0)}; cuentas de caja sin saldo de referencia: "
        f"{_pct(facts.get('no_cash_anchor_share') or 0.0)}."
    )
    if facts.get("limit_assumed_constant"):
        evidence += " El límite de las líneas se asume constante."
    return _attribute("data_quality", QUALITY_LABELS[code], evidence, 1.0)


def _treasury_attribute(facts: Mapping[str, Any]) -> ProfileAttribute:
    code, buffer = treasury_class(facts)
    if code is None:
        anchored = facts.get("cash_month_end") is not None and facts.get("n_cash_products")
        return _attribute(
            "treasury_structure", None,
            "Caja no positiva y sin salidas recientes con las que medir un colchón." if anchored
            else "Ninguna cuenta de caja tiene un saldo de referencia para reconstruir la tesorería.", 0.0,
        )
    cash, headroom = facts["cash_month_end"], facts.get("headroom") or 0.0
    evidence = f"Caja de cierre {_money(cash)} y {_money(headroom)} disponibles en líneas"
    if buffer is not None:
        evidence += f": {_num(buffer, 1)} meses de salidas medianas"
    evidence += (
        f"; {_num(facts.get('neg_cash_months_6m') or 0)} de los últimos {OVERDRAWN_WINDOW_MONTHS} meses "
        "cerraron en negativo."
    )
    if code == "swept_subsidiary":
        share = max(0.0, facts.get("cash_share_of_group") or 0.0)
        evidence += f" Conserva el {_pct(share)} de la caja del grupo: su liquidez se lee en el grupo."
    if code == "line_funded":
        evidence += f" Líneas dispuestas al {_pct(facts['drawn'] / facts['granted'])}."
    anchored = 1.0 - (facts.get("no_cash_anchor_share") or 0.0)
    return _attribute("treasury_structure", TREASURY_LABELS[code], evidence, anchored)


def _financing_attribute(debts: Sequence[Mapping[str, Any]], facts: Mapping[str, Any]) -> ProfileAttribute:
    service = facts.get("debt_service_sum_12m_w") or 0.0
    code, short = financing_class(debts, int(facts.get("debt_service_months") or 0))
    outflow = facts.get("outflow_median_3m") or facts.get("outflow_median_12m")
    band, months = headroom_band(facts.get("headroom") or 0.0, outflow, int(facts.get("n_credit_lines") or 0))
    if code == "no_debt":
        return _attribute(
            "financing_profile", FINANCING_LABELS[code],
            "Sin productos de deuda conectados ni servicio de deuda recurrente en los últimos 12 meses.", 1.0,
        )
    if code == "unconnected_debt":
        return _attribute(
            "financing_profile", FINANCING_LABELS[code],
            f"Amortiza deuda en {_plural(int(facts['debt_service_months']), 'mes', 'meses')} de los últimos 12 "
            f"(servicio de deuda de {_money(service)}) sin ningún producto de deuda conectado.", 0.3,
        )
    value = FINANCING_LABELS[code] + (f" · {HEADROOM_LABELS[band]}" if band else "")
    kinds = Counter(item["type"] for item in debts)
    listed = ", ".join(
        _plural(count, *_DEBT_TYPE_NAMES.get(kind, (kind, kind))) for kind, count in sorted(kinds.items())
    )
    drawn = sum(item["drawn"] for item in debts)
    evidence = (
        f"{_plural(len(debts), 'producto de deuda', 'productos de deuda')} ({listed}); dispuesto "
        f"{_money(drawn)}, {_pct(short)} a corto plazo."
    )
    if months is not None:
        evidence += f" Disponible en líneas: {_num(months, 1)} meses de salidas."
    inflow = facts.get("op_in_sum_12m_w") or 0.0
    if inflow > 0:
        evidence += f" Dispuesto = {_num(drawn / inflow, 2)}× los cobros de 12 meses."
    evidence += " Foto de la fecha de extracción; los límites se asumen constantes."
    known = sum(1 for item in debts if item["known"]) / len(debts)
    return _attribute("financing_profile", value, evidence, known)


def _industry_context(item: IndustryClassification | None) -> dict[str, Any] | None:
    if item is None:
        return None
    reason = item.reason
    if item.source == "insufficient_data" or item.confidence < 0.5:
        reason = f"Clasificación de baja confianza. {reason}"
    return {
        "slug": item.industry_slug, "label": item.industry_label,
        "confidence": float(item.confidence), "reason": reason[:400],
    }


def _group_industry(members: Sequence[IndustryClassification]) -> dict[str, Any] | None:
    usable = [item for item in members if item.source != "insufficient_data"] or list(members)
    if not usable:
        return None
    score: dict[str, list[float]] = defaultdict(list)
    for item in usable:
        score[item.industry_slug].append(float(item.confidence))
    slug = min(score, key=lambda key: (-len(score[key]), -sum(score[key]), key))
    label = next(item.industry_label for item in usable if item.industry_slug == slug)
    confidence = sum(score[slug]) / len(usable)
    return {
        "slug": slug, "label": label, "confidence": round(min(1.0, confidence), 4),
        "reason": (
            f"Arquetipo más frecuente del grupo: {_num(len(score[slug]))} de "
            f"{_plural(len(usable), 'empresa clasificada', 'empresas clasificadas')}."
        ),
    }


# --------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Structure:
    """Group structure as of the month: members, sweeps and simplified liquidity facts."""

    company_facts: dict[str, dict[str, Any]]
    group_facts: dict[str, dict[str, Any]]
    pairs: list[dict[str, Any]]  # intra-group mirror pairs of the trailing 12 months
    touching: Counter[str]  # pairs per company
    group_pairs: Counter[str]  # pairs per group
    members: dict[str, list[str]]  # group -> companies with booked rows, sorted


@dataclass(frozen=True)
class _Evidence:
    """Everything the rules read, per company and per group."""

    company_stats: dict[str, dict[str, Any]]
    group_stats: dict[str, dict[str, Any]]
    company_facts: dict[str, dict[str, Any]]  # from the panel, else from the structure
    group_facts: dict[str, dict[str, Any]]
    structure: _Structure


def _structure(frames: _Frames, asof: pl.DataFrame, params: Params, *, liquidity: bool) -> _Structure:
    """``liquidity`` False skips the back-roll (a panel provides those facts)."""
    start = _month_add(frames.last_month, -11)
    pairs = _sweep_pairs(asof.filter(pl.col("month") >= start))
    group_of = dict(frames.companies.select("company_id", "group_id").iter_rows())
    booked = set(asof["company_id"].unique().to_list())
    members: dict[str, list[str]] = defaultdict(list)
    for company_id in sorted(booked & set(group_of)):
        members[group_of[company_id]].append(company_id)

    touching: Counter[str] = Counter()
    paid: Counter[str] = Counter()
    net_paid: dict[str, float] = defaultdict(float)
    group_pairs: Counter[str] = Counter()
    for pair in pairs:
        touching.update({pair["out_company"], pair["in_company"]})
        paid[pair["out_company"]] += 1
        net_paid[pair["out_company"]] += pair["eur"] or 0.0
        net_paid[pair["in_company"]] -= pair["eur"] or 0.0
        group_pairs[pair["group_id"]] += 1

    company_facts: dict[str, dict[str, Any]] = {}
    group_facts: dict[str, dict[str, Any]] = {}
    if liquidity:
        company_facts, group_facts = _liquidity_facts(frames, asof, params)
        for group_id, companies in members.items():
            group_facts.setdefault(group_id, {}).update(n_members=len(companies), swept_subsidiary=False)
            for company_id in companies:
                facts = company_facts.setdefault(company_id, {})
                facts.update(
                    n_members=len(companies), sweep_pairs_12m=touching[company_id],
                    sweep_pairs_out_12m=paid[company_id], intragroup_net_payer=net_paid[company_id] > 0,
                )
                facts["swept_subsidiary"] = is_swept(facts, params)
    return _Structure(company_facts, group_facts, pairs, touching, group_pairs, dict(members))


def _gather(frames: _Frames, asof: pl.DataFrame, panel: pl.DataFrame | None, params: Params) -> _Evidence:
    last = frames.last_month
    start = _month_add(last, -11)
    company_stats = _transaction_stats(asof, "company_id", start, params)
    group_stats = _transaction_stats(asof, "group_id", start, params)
    from_panel = panel is not None and not panel.is_empty()
    structure = _structure(frames, asof, params, liquidity=not from_panel)
    company_facts, group_facts = structure.company_facts, structure.group_facts

    if from_panel:
        rows = _panel_facts(panel, last)
        company_facts = {key[1]: value for key, value in rows.items() if key[0] == "company"}
        group_facts = {key[1]: value for key, value in rows.items() if key[0] == "group"}
    else:
        has_invoices: set[str] = set()
        if frames.invoices is not None and not frames.invoices.is_empty():
            invoices = frames.invoices.filter(pl.col("issuance_date") <= _month_end(last))
            if "document_type" in invoices.columns:
                invoices = invoices.filter(pl.col("document_type") == "invoice")
            has_invoices = set(invoices["company_id"].unique().to_list())
        shares = ("dash_share", "fx_excluded_share", "orphan_product_share")
        for stats, facts in ((company_stats, company_facts), (group_stats, group_facts)):
            for entity_id, entry in stats.items():
                values = facts.setdefault(entity_id, {})
                values.update(_flow_facts(entry, last, params))
                values.update({name: entry.get(name) for name in shares})
                owners = structure.members.get(entity_id, [entity_id])
                values["has_invoices"] = any(company_id in has_invoices for company_id in owners)
    return _Evidence(company_stats, group_stats, company_facts, group_facts, structure)


def swept_subsidiaries(
    tables: Any, cleaned: Any = None, params: Params | None = None, *, month: date | None = None
) -> set[str]:
    """Companies whose cash is swept to their group, as of ``month``.

    ``tables`` is ``io.Tables`` or ``CleanTables``; ``cleaned`` is ``CleanTables``
    or the clean transactions frame (None: mirrors come from a simple stand-in).
    Structure only: group membership, zero-balance cash accounts, intra-group
    mirror pairs the company pays and its share of the group cash (``is_swept``).
    Reads rows dated up to the end of ``month`` (default: the last month of the
    window) plus the balance anchor of the back-roll, so the answer for a month
    does not change when later rows arrive.
    """
    if params is None:
        from .params import load_params

        params = load_params()
    frames = _frames(tables, cleaned, params, month)
    asof = frames.transactions.filter(pl.col("date") <= _month_end(frames.last_month))
    facts = _structure(frames, asof, params, liquidity=True).company_facts
    return {company_id for company_id, values in facts.items() if values.get("swept_subsidiary")}


def _roles(evidence: _Evidence, debts: Mapping[str, list[dict[str, Any]]], params: Params) -> dict[str, str]:
    """Group role per company with booked rows; first rule that applies.

    standalone (single member) -> shell (no operating flow in 12 months) ->
    captive (no external inflow, funded by the group) -> swept subsidiary ->
    treasury centre (counterparty of at least half of the pairs of the swept
    and captive members, or the single hub of the pairs of a group of three or
    more) -> financing hub (most of the drawn debt of such a group) -> operating.
    """
    structure = evidence.structure
    partners: dict[str, Counter[str]] = defaultdict(Counter)
    received: Counter[str] = Counter()
    for pair in structure.pairs:
        partners[pair["out_company"]][pair["in_company"]] += 1
        partners[pair["in_company"]][pair["out_company"]] += 1
        received[pair["in_company"]] += 1
    roles: dict[str, str] = {}
    minimum = params.liquidity.swept_pairs_min
    for group_id, companies in structure.members.items():
        if len(companies) == 1:
            roles[companies[0]] = "standalone"
            continue
        dependent: set[str] = set()
        for company_id in companies:
            flows = list(evidence.company_stats[company_id].get("monthly", {}).values())
            inflow = sum(month.get("op_in", 0.0) for month in flows)
            outflow = sum(month.get("op_out", 0.0) + month.get("debt_service", 0.0) for month in flows)
            if inflow == 0 and outflow == 0:
                roles[company_id] = "shell"
            elif inflow == 0 and received[company_id] > 0:
                roles[company_id] = "captive"
                dependent.add(company_id)
            elif evidence.company_facts.get(company_id, {}).get("swept_subsidiary"):
                roles[company_id] = "swept_subsidiary"
                dependent.add(company_id)
        large = len(companies) >= FINANCING_HUB_MIN_MEMBERS
        touched = {c: sum(partners[c].values()) for c in companies}
        served = {c: sum(n for other, n in partners[c].items() if other in dependent) for c in companies}
        swept_pairs = sum(served[c] for c in companies if c not in dependent)
        busiest = max(touched.values())
        drawn = {c: sum(item["drawn"] for item in debts.get(c, [])) for c in companies}
        for company_id in companies:
            if company_id in roles:
                continue
            centre = served[company_id] >= max(minimum, CENTRE_MIN_PAIR_SHARE * swept_pairs)
            hub = (
                large
                and touched[company_id] >= max(minimum, CENTRE_MIN_PAIR_SHARE * structure.group_pairs[group_id])
                and touched[company_id] == busiest and list(touched.values()).count(busiest) == 1
            )
            if centre or hub:
                roles[company_id] = "treasury_centre"
            elif large and sum(drawn.values()) > 0 and (
                drawn[company_id] / sum(drawn.values()) >= FINANCING_HUB_MIN_SHARE
            ):
                roles[company_id] = "financing_hub"
            else:
                roles[company_id] = "operating_subsidiary"
    return roles


def _debts(frames: _Frames, params: Params) -> dict[str, list[dict[str, Any]]]:
    """Debt products per company (contingent types aside), EUR at the static rate."""
    excluded = list(params.flows.excluded_debt_types)
    products = frames.products.filter(
        (pl.col("product_family") == "debt") & ~pl.col("product_type").is_in(excluded)
    ).sort("product_id")
    debts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in products.to_dicts():
        rate = params.fx.rates.get(row["currency"])
        if rate is None:
            continue
        owed = row["outstanding_cents"]
        debts[row["company_id"]].append({
            "type": row["product_type"],
            # a positive balance on a line is a credit balance, not debt
            "drawn": max(0, -(owed or 0)) / 100 * rate,
            "granted": abs(row["granted_cents"] or 0) / 100 * rate,
            "custom": row["service"] == "custom" or (row["bank_name"] or "").lower().startswith("other ("),
            "known": owed is not None,
        })
    return debts


def _invested(frames: _Frames, params: Params) -> dict[str, float]:
    """Savings and investment balances per company, back-rolled to the end of the month, EUR."""
    anchors = _anchors(frames, params).filter(pl.col("product_type").is_in(list(INVESTED_PRODUCT_TYPES)))
    rolled = _balances_at(frames.transactions, anchors, [_month_end(frames.last_month)])
    invested: dict[str, float] = defaultdict(float)
    for row in rolled.sort("product_id").to_dicts():
        if row["fx_rate"] is not None:
            invested[row["company_id"]] += max(0, row["balance_0"]) / 100 * row["fx_rate"]
    return invested


def _role_attribute(role: str | None, evidence: _Evidence, company_id: str, group_id: str) -> ProfileAttribute:
    if role is None:
        return _attribute("group_role", None, "Sin movimientos bancarios: el rol no se puede inferir.", 0.0)
    members = evidence.structure.members.get(group_id, [])
    facts = evidence.company_facts.get(company_id, {})
    pairs = evidence.structure.touching[company_id]
    if role == "standalone":
        text = "Es la única empresa del grupo con movimientos bancarios."
    else:
        text = (
            f"Grupo de {_plural(len(members), 'empresa', 'empresas')} con movimientos; participa en "
            f"{_plural(pairs, 'par de traspasos intragrupo', 'pares de traspasos intragrupo')} en 12 meses"
        )
        share = facts.get("cash_share_of_group")
        text += f" y conserva el {_pct(max(0.0, share))} de la caja del grupo." if share is not None else "."
    coverage = 1.0 if role == "standalone" else min(1.0, (facts.get("months_observed") or 0) / 12)
    return _attribute("group_role", GROUP_ROLE_LABELS[role], text, coverage)


def _structure_attribute(group_id: str, evidence: _Evidence, roles: Mapping[str, str]) -> ProfileAttribute:
    members = evidence.structure.members.get(group_id, [])
    if not members:
        return _attribute("group_role", None, "Ninguna empresa del grupo tiene movimientos bancarios.", 0.0)
    counts = Counter(roles[company_id] for company_id in members)
    if len(members) == 1:
        code = "single_company"
    elif counts["treasury_centre"] or counts["swept_subsidiary"] or counts["captive"]:
        code = "centralised_treasury"
    elif counts["financing_hub"]:
        code = "centralised_financing"
    else:
        code = "independent_members"
    pairs = evidence.structure.group_pairs[group_id]
    listed = ", ".join(
        f"{count} × {GROUP_ROLE_LABELS[role].lower()}" for role, count in sorted(counts.items())
    )
    text = (
        f"{_plural(len(members), 'empresa', 'empresas')} con movimientos ({listed}); "
        f"{_plural(pairs, 'par de traspasos intragrupo', 'pares de traspasos intragrupo')} en 12 meses."
    )
    months = evidence.group_facts.get(group_id, {}).get("months_observed") or 0
    coverage = 1.0 if len(members) == 1 else min(1.0, months / 12)
    return _attribute("group_role", GROUP_STRUCTURE_LABELS[code], text, coverage)


def build_profiles(
    clean: CleanTables,
    panel: pl.DataFrame | None,
    params: Params,
    industry: Mapping[str, IndustryClassification] | None = None,
) -> dict[str, ProfileCard]:
    """One card per company and per group, keyed by entity_id, as of
    ``clean.window.last_month``.

    ``attributes`` follow ``PROFILE_KEYS`` order, one ``ProfileAttribute`` per
    key, always present: an attribute that cannot be inferred has ``value``
    None and ``coverage`` 0. ``evidence`` is a Spanish sentence built from
    aggregates (counts, shares, amounts), never from a raw description.
    ``panel`` follows ``PANEL_COLUMNS``; None or empty switches to the
    simplified back-roll of this module. ``clean`` may be the cached
    ``io.Tables``: missing clean columns get simple stand-ins.
    ``size_band``: ``SIZE_BAND_LABELS`` of the panel band of the last month.
    ``customer_concentration``: flagged when the top counterparty
    (``counterparty_key``) holds at least ``profile.concentration_top1_share``
    of the total op_in of the month in at least ``concentration_min_months`` of
    the trailing ``concentration_window_months``; internal rows never count, so
    a sister company cannot be the top customer. It stays on the card: it is
    not a pillar input and not an alert.
    ``seasonality``: value None; with two years of history the month of the
    year is not distinguishable from noise, and the sentence says so.
    ``financing_profile`` states that limits are assumed constant.
    ``industry`` maps company_id to its classification; it lands in
    ``context["industry"]`` (slug, label, confidence, reason) for companies and
    as the modal member slug for groups. Context only: low-confidence labels
    are shown as such and never gate or scale anything.
    """
    frames = _frames(clean, clean, params, None)
    last = frames.last_month
    asof = frames.transactions.filter(pl.col("date") <= _month_end(last))
    evidence = _gather(frames, asof, panel, params)
    industry = industry or {}
    debts = _debts(frames, params)
    invested = _invested(frames, params)
    roles = _roles(evidence, debts, params)

    companies = frames.companies.sort("company_id").to_dicts()
    group_erp: dict[str, str | None] = {}
    if "erp" in frames.groups.columns:
        group_erp = dict(frames.groups.select("group_id", "erp").iter_rows())
    banks: dict[str, list[str | None]] = defaultdict(list)
    terminals: set[str] = set()
    banking = frames.products.filter(pl.col("product_family") == "banking").sort("product_id")
    for company_id, bank, kind in banking.select("company_id", "bank_name", "product_type").iter_rows():
        banks[company_id].append(bank)
        if kind == "tpv":
            terminals.add(company_id)
    undeclared = [row["company_id"] for row in companies if normalise_country(row["country"]) is None]
    language = _language_hits(asof, undeclared)

    def shared(stats: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, ProfileAttribute]:
        return {
            "size_band": _size_attribute(facts),
            "treasury_structure": _treasury_attribute(facts),
            "history_depth": _history_attribute(
                facts.get("months_observed") or 0, stats.get("first_month"), params
            ),
            "seasonality": _seasonality_attribute(),
            "customer_concentration": _concentration_attribute(stats, last, params),
            "payment_policy": _payment_attribute(stats),
            "data_quality": _quality_attribute(facts, params),
        }

    cards: dict[str, ProfileCard] = {}
    countries: dict[str, list[tuple[str | None, float]]] = defaultdict(list)
    rows_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in companies:
        company_id, group_id = row["company_id"], row["group_id"]
        rows_of[group_id].append(row)
        stats = dict(evidence.company_stats.get(company_id, {}))
        stats["has_pos_terminal"] = company_id in terminals
        facts = dict(evidence.company_facts.get(company_id, {}))
        facts["invested"] = invested.get(company_id, 0.0)
        facts["debt_service_months"] = stats.get("repayment_months", 0)
        role = roles.get(company_id)
        code, sentence, share = infer_country(row["country"], language.get(company_id), banks[company_id])
        countries[group_id].append((code, share))
        has_invoices = bool(facts.get("has_invoices"))
        attributes = {
            **shared(stats, facts),
            "country": _attribute("country", _country_value(code) if code else None, sentence, share),
            "erp_tier": _erp_attribute(row["erp"], group_erp.get(group_id), has_invoices, "la empresa"),
            "group_role": _role_attribute(role, evidence, company_id, group_id),
            "financing_profile": _financing_attribute(debts.get(company_id, []), facts),
            "revenue_model": _revenue_attribute(stats, role == "captive"),
        }
        cards[company_id] = ProfileCard(
            entity_kind="company", entity_id=company_id, group_id=group_id, as_of_month=last,
            attributes=tuple(attributes[key] for key in PROFILE_KEYS),
            context={"industry": _industry_context(industry.get(company_id))},
        )

    group_cards: dict[str, ProfileCard] = {}
    for group_id in sorted({*frames.groups["group_id"].to_list(), *rows_of}):
        member_ids = [row["company_id"] for row in rows_of.get(group_id, [])]
        stats = dict(evidence.group_stats.get(group_id, {}))
        stats["has_pos_terminal"] = any(company_id in terminals for company_id in member_ids)
        facts = dict(evidence.group_facts.get(group_id, {}))
        facts["invested"] = sum(invested.get(company_id, 0.0) for company_id in member_ids)
        facts["debt_service_months"] = stats.get("repayment_months", 0)
        facts["swept_subsidiary"] = False
        pooled = [item for company_id in member_ids for item in debts.get(company_id, [])]
        erps = Counter(row["erp"] for row in rows_of.get(group_id, []) if (row["erp"] or "").strip())
        modal_erp = min(erps.items(), key=lambda item: (-item[1], item[0]))[0] if erps else None
        has_invoices = bool(facts.get("has_invoices"))
        attributes = {
            **shared(stats, facts),
            "country": _group_country(countries.get(group_id, [])),
            "erp_tier": _erp_attribute(group_erp.get(group_id) or modal_erp, None, has_invoices, "el grupo"),
            "group_role": _structure_attribute(group_id, evidence, roles),
            "financing_profile": _financing_attribute(pooled, facts),
            "revenue_model": _revenue_attribute(stats, False),
        }
        classified = [industry[company_id] for company_id in member_ids if company_id in industry]
        group_cards[group_id] = ProfileCard(
            entity_kind="group", entity_id=group_id, group_id=group_id, as_of_month=last,
            attributes=tuple(attributes[key] for key in PROFILE_KEYS),
            context={"industry": _group_industry(classified)},
        )
    return {**group_cards, **cards}


def coverage_report(cards: Mapping[str, ProfileCard], entity_kind: str = "company") -> dict[str, float]:
    """Share of cards of one kind with a value, per attribute (aggregate only)."""
    chosen = [card for card in cards.values() if card.entity_kind == entity_kind]
    if not chosen:
        return {key: 0.0 for key in PROFILE_KEYS}
    filled: Counter[str] = Counter()
    for card in chosen:
        filled.update(item.key for item in card.attributes if item.value is not None)
    return {key: filled[key] / len(chosen) for key in PROFILE_KEYS}


__all__ = [
    "PROFILE_LABELS",
    "bank_country",
    "build_profiles",
    "coverage_report",
    "erp_tier",
    "financing_class",
    "headroom_band",
    "history_class",
    "infer_country",
    "is_swept",
    "normalise_country",
    "payment_policy",
    "quality_factor",
    "revenue_model",
    "swept_subsidiaries",
    "treasury_class",
]
