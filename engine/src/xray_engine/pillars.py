"""Five pillars, 0-100, from frozen anchor tables. Pure: no I/O, no frames.

Every function reads one ``PanelRow`` (pre-aggregated as-of facts) and
``Params`` and returns a ``PillarResult`` whose ``inputs`` carry exactly
``PILLAR_INPUT_KEYS[key]``. ``score`` is None when the pillar is not
observable, always with a gate: a missing pillar is never imputed, its weight
is renormalised by the aggregate. An undefined or zero denominator gives None,
never 0 or 100. Money only enters through ratios, so scores do not depend on
the money scale (``size_band`` arrives as a label). No smoothing, no seasonal
factors. ``evidence`` holds aggregate facts with Spanish labels, ``period`` as
``YYYY-MM``, ``YYYY-MM-DD`` or a closed range joined by ``..`` and the source
file name; rows without a value are left out. ``pillar_note`` renders the one
sentence shown next to a pillar from ``NOTE_TEMPLATES`` and the inputs.
"""

from __future__ import annotations

from datetime import date, timedelta

from .contracts import (
    GATE_TEXTS,
    PILLAR_INPUT_KEYS,
    SIZE_BANDS,
    Anchors,
    Evidence,
    PanelRow,
    Params,
    PillarResult,
)

TRANSACTIONS = "transactions.csv"
BALANCES = "balances.csv"
INVOICES = "invoices.csv"
DEBT_PRODUCTS = "debt_products.csv"

# Gates that describe how a score was obtained; every other gate blocks it.
INFORMATIVE_GATES: tuple[str, ...] = (
    "inherited_from_group",
    "absolute_anchors",
    "coverage_only",
    "momentum_only",
    "carried_forward",
)

NOTE_MAX_DAYS = 365  # a longer buffer reads "más de 365 días"

# One sentence per pillar; the placeholders are filled from PillarResult.inputs.
NOTE_TEMPLATES: dict[str, str] = {
    "liquidity": "Colchón de {end} de salidas entre caja y líneas disponibles ({low} en el mínimo del mes).",
    "liquidity_negative": "Caja más líneas disponibles en negativo a fin de mes: no cubre ningún día de salidas.",
    "liquidity_inherited": "Liquidez del grupo: colchón de {end} de salidas ({low} en el mínimo del mes).",
    "payments_late": "Paga a proveedores {days} después del vencimiento, ponderado por importe.",
    "payments_early": "Paga a proveedores {days} antes del vencimiento, ponderado por importe.",
    "collections_late": "Cobra de clientes {days} después del vencimiento, ponderado por importe.",
    "collections_early": "Cobra de clientes {days} antes del vencimiento, ponderado por importe.",
    "activity": (
        "Los cobros operativos cubren {coverage} veces los pagos de los últimos {months} meses "
        "y los cobros recientes son {momentum} veces los de los meses previos."
    ),
    "activity_coverage": "Los cobros operativos cubren {coverage} veces los pagos de los últimos {months} meses.",
    "activity_momentum": (
        "Los cobros de los últimos {recent} meses son {momentum} veces los de los meses previos, "
        "con las mismas cuentas."
    ),
    "debt": "El servicio de la deuda consume el {burden} % de los cobros de {months} meses.",
    "unavailable": "Pilar no observable este mes.",
}


def format_es(value: float, decimals: int = 0) -> str:
    """Number with a decimal comma, as shown on screen."""
    text = f"{value:.{decimals}f}"
    if float(text) == 0:
        text = text.lstrip("-")  # no "-0,0" on screen
    return text.replace(".", ",")


def _days_es(value: float, ceiling: int | None = None) -> str:
    count = abs(round(value))
    if ceiling is not None and count > ceiling:
        return f"más de {ceiling} días"
    return f"{count} día" if count == 1 else f"{count} días"


def _known(value: float | None) -> bool:
    return value is not None and value == value  # NaN reads as missing


def _positive(value: float | None) -> bool:
    return value is not None and value > 0


def _shift(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _span(month: date, length: int, end_back: int = 0) -> str:
    """``length`` months ending ``end_back`` months before ``month``."""
    last = _shift(month, -end_back)
    if length <= 1:
        return f"{last.year:04d}-{last.month:02d}"
    first = _shift(last, 1 - length)
    return f"{first.year:04d}-{first.month:02d}..{last.year:04d}-{last.month:02d}"


def _observed(row: PanelRow, window: int) -> int:
    # windows only hold observed months; synthetic rows may not say how many
    return min(window, row.months_observed) if (row.months_observed or 0) > 0 else window


def _facts(*rows: Evidence) -> tuple[Evidence, ...]:
    return tuple(row for row in rows if row.value is not None)


def _result(
    key: str,
    score: float | None,
    inputs: dict[str, float | None],
    gates: list[str],
    evidence: tuple[Evidence, ...],
) -> PillarResult:
    if score is not None:
        score = min(100.0, max(0.0, score))
    full = {name: inputs.get(name) for name in PILLAR_INPUT_KEYS[key]}
    return PillarResult(key=key, score=score, inputs=full, gates=tuple(gates), evidence=evidence)


def liquidity_anchors(row: PanelRow, p: Params) -> tuple[Anchors, bool]:
    """(table, segmented). The size-band table of ``row.size_band`` when
    ``p.liquidity.segmented`` and the band is known, else the absolute table
    ``p.anchors["liquidity"]``."""
    if p.liquidity.segmented and row.size_band in SIZE_BANDS:
        return p.liquidity.band_anchors[row.size_band], True
    return p.anchors["liquidity"], False


def pillar_liquidity(
    row: PanelRow, p: Params, group_row: PanelRow | None = None
) -> PillarResult:
    """Liquidity: days of outflow covered by cash plus undrawn lines.

    ``monthly_outflow = outflow_median_3m`` when positive, else
    ``outflow_median_12m`` when positive, else None (gate ``buffer_undefined``).
    ``buffer_days = (cash + headroom) / (monthly_outflow / days_per_month)`` at
    month end (``cash_month_end + headroom``) and at the intra-month minimum
    (``cash_intra_month_min + headroom_at_min``);
    ``score = month_end_weight * A(end) + intra_min_weight * A(min)`` with
    ``A = liquidity_anchors``; gate ``absolute_anchors`` when the table is not
    segmented. Headroom lives in this pillar only.
    When ``row.swept_subsidiary`` and ``group_row`` is given, everything is
    computed from ``group_row`` (its size band included) and the gate
    ``inherited_from_group`` is added.
    None with gate ``no_cash_anchor`` when cash is None; both blocking gates
    are reported when both apply.
    """
    cfg = p.liquidity
    inherited = bool(row.swept_subsidiary) and group_row is not None
    source = group_row if inherited else row
    gates = ["inherited_from_group"] if inherited else []

    monthly, window = None, cfg.outflow_window_months
    if _positive(source.outflow_median_3m):
        monthly = source.outflow_median_3m
    elif _positive(source.outflow_median_12m):
        monthly, window = source.outflow_median_12m, cfg.outflow_fallback_months
    cash_known = _known(source.cash_month_end) and _known(source.cash_intra_month_min)
    headroom, headroom_at_min = source.headroom or 0.0, source.headroom_at_min or 0.0
    inputs: dict[str, float | None] = {
        "cash_month_end": source.cash_month_end,
        "cash_intra_month_min": source.cash_intra_month_min,
        "headroom": headroom,
        "headroom_at_min": headroom_at_min,
        "monthly_outflow": monthly,
    }
    if not cash_known:
        gates.append("no_cash_anchor")
    if monthly is None:
        gates.append("buffer_undefined")

    score = None
    if cash_known and monthly is not None:
        daily = monthly / cfg.days_per_month
        end = (source.cash_month_end + headroom) / daily
        low = (source.cash_intra_month_min + headroom_at_min) / daily
        table, segmented = liquidity_anchors(source, p)
        if not segmented:
            gates.append("absolute_anchors")
        score_end, score_low = table(end), table(low)
        score = cfg.month_end_weight * score_end + cfg.intra_min_weight * score_low
        inputs.update(
            buffer_days_month_end=end,
            buffer_days_intra_min=low,
            score_month_end=score_end,
            score_intra_min=score_low,
        )

    whose = " del grupo" if inherited else ""
    month = _span(source.month, 1)
    has_lines = (source.n_credit_lines or 0) > 0 or headroom > 0 or headroom_at_min > 0
    evidence = _facts(
        Evidence(f"Caja{whose} a fin de mes", source.cash_month_end if cash_known else None,
                 "EUR", month, BALANCES),
        Evidence(f"Caja mínima{whose} dentro del mes",
                 source.cash_intra_month_min if cash_known else None, "EUR", month, BALANCES),
        Evidence(f"Disponible{whose} en líneas de crédito a fin de mes",
                 headroom if has_lines else None, "EUR", month, DEBT_PRODUCTS),
        Evidence(f"Mediana mensual{whose} de pagos operativos y deuda", monthly, "EUR",
                 _span(source.month, _observed(source, window)), TRANSACTIONS),
        Evidence(f"Días de colchón{whose} a fin de mes", inputs.get("buffer_days_month_end"),
                 "días", month, BALANCES),
        Evidence(f"Días de colchón{whose} en el mínimo del mes",
                 inputs.get("buffer_days_intra_min"), "días", month, BALANCES),
    )
    return _result("liquidity", score, inputs, gates, evidence)


def _punctuality(key: str, side: str, party: str, row: PanelRow, p: Params) -> PillarResult:
    cfg = p.invoices
    count = getattr(row, f"{side}_n") or 0
    neff = getattr(row, f"{side}_neff")
    amount = getattr(row, f"{side}_amount")
    days = getattr(row, f"{side}_days_beyond_terms")
    stamped = getattr(row, f"{side}_stamped_share")
    open_share = getattr(row, f"{side}_open_share")
    inputs: dict[str, float | None] = {
        "days_beyond_terms": days,
        "n": float(count),
        "neff": neff,
        "amount": amount,
        "stamped_share": stamped,
        "open_share": open_share,
    }
    gates: list[str] = []
    if not _known(stamped):
        gates.append("no_invoices")
    else:
        if stamped >= cfg.stamped_share_max:
            gates.append("stamped_regime")
        if count < cfg.min_invoices:
            gates.append("few_invoices")
        if not _known(neff) or neff < cfg.min_effective_n:
            gates.append("low_effective_n")
        aged = getattr(row, f"{side}_aged_n") or 0
        still_open = getattr(row, f"{side}_aged_open_n") or 0
        if aged >= cfg.never_settles_min_aged and still_open >= cfg.never_settles_open_share * aged:
            gates.append("erp_never_settles")
        if not gates and not _known(days):
            gates.append("no_invoices")  # inconsistent row: nothing to measure
    score = None if gates else p.anchors[key](days)

    month_end = _shift(row.month, 1) - timedelta(days=1)
    first_day = month_end - timedelta(days=cfg.window_days - 1)
    period = f"{first_day.isoformat()}..{month_end.isoformat()}"
    seen = _known(stamped)
    evidence = _facts(
        Evidence("Días sobre el vencimiento, ponderados por importe", days if _known(days) else None,
                 "días", period, INVOICES, count),
        Evidence(f"Facturas de {party} con fechas reales en la ventana", count if seen else None,
                 "facturas", period, INVOICES, count),
        Evidence("Facturas efectivas por concentración de importe (n de Kish)",
                 neff if _known(neff) else None, "facturas", period, INVOICES, count),
        Evidence(f"Importe de las facturas de {party} en la ventana", amount if count else None,
                 "EUR", period, INVOICES, count),
        Evidence("Facturas con fechas estampadas por el ERP", stamped if seen else None,
                 "cuota", period, INVOICES),
        Evidence("Importe de la ventana aún abierto a fin de mes",
                 open_share if _known(open_share) else None, "cuota", period, INVOICES, count),
    )
    return _result(key, score, inputs, gates, evidence)


def pillar_payments(row: PanelRow, p: Params) -> PillarResult:
    """Payments to suppliers: as-of AP days beyond terms (anchors ``payments``).

    ``score = A(ap_days_beyond_terms)``. None with gate ``no_invoices`` when no
    AP invoice is due in the window (``ap_stamped_share`` is None); else None
    with every gate that applies, in this order: ``stamped_regime``
    (``ap_stamped_share >= stamped_share_max``), ``few_invoices``
    (``ap_n < min_invoices``), ``low_effective_n`` (``ap_neff`` None or
    ``< min_effective_n``), ``erp_never_settles`` (``ap_aged_n >=
    never_settles_min_aged`` and ``ap_aged_open_n >= never_settles_open_share *
    ap_aged_n``: the ERP does not record payments, open invoices are no signal).
    Never a neutral value.
    """
    return _punctuality("payments", "ap", "proveedores", row, p)


def pillar_collections(row: PanelRow, p: Params) -> PillarResult:
    """Collections from customers: same as payments on the ``ar_*`` columns
    (anchors ``collections``). A separate pillar, never averaged with AP."""
    return _punctuality("collections", "ar", "clientes", row, p)


def pillar_activity(row: PanelRow, p: Params) -> PillarResult:
    """Activity: mean of the available sub-scores.

    coverage = ``op_in_sum_6m_w / outflow_sum_6m_w`` (anchors
      ``activity_coverage``); needs ``months_in_6m_window >=
      coverage_min_months`` and a positive denominator, else gate
      ``coverage_undefined``;
    momentum = ``op_in_lfl_recent_mean / op_in_lfl_prior_mean`` (anchors
      ``activity_momentum``); needs ``months_observed >= min_months_observed``
      (else gate ``short_history``), ``lfl_prior_months >= min_prior_months``
      and both means present with a positive prior (else gate ``no_base``).
    One sub-score alone takes the pillar (gate ``coverage_only`` or
    ``momentum_only``); none gives None. ``row.no_external_revenue`` gives None
    with gate ``no_external_revenue`` before anything else.
    """
    cfg = p.activity
    recent, prior = row.op_in_lfl_recent_mean, row.op_in_lfl_prior_mean
    inputs: dict[str, float | None] = {
        "op_in_6m": row.op_in_sum_6m_w,
        "outflow_6m": row.outflow_sum_6m_w,
        "lfl_recent_mean": recent,
        "lfl_prior_mean": prior,
    }
    gates: list[str] = []
    scores: dict[str, float] = {}
    if row.no_external_revenue:
        gates.append("no_external_revenue")
    else:
        observed = (row.months_in_6m_window or 0) >= cfg.coverage_min_months
        if observed and _known(row.op_in_sum_6m_w) and _positive(row.outflow_sum_6m_w):
            inputs["coverage"] = row.op_in_sum_6m_w / row.outflow_sum_6m_w
            scores["coverage"] = p.anchors["activity_coverage"](inputs["coverage"])
        else:
            gates.append("coverage_undefined")
        if (row.months_observed or 0) < cfg.min_months_observed:
            gates.append("short_history")
        elif (row.lfl_prior_months or 0) < cfg.min_prior_months or not _known(recent) or not _positive(prior):
            gates.append("no_base")
        else:
            inputs["momentum"] = recent / prior
            scores["momentum"] = p.anchors["activity_momentum"](inputs["momentum"])
        if len(scores) == 1:
            gates.append(f"{next(iter(scores))}_only")
    inputs["score_coverage"] = scores.get("coverage")
    inputs["score_momentum"] = scores.get("momentum")
    score = sum(scores.values()) / len(scores) if scores else None

    window = _span(row.month, row.months_in_6m_window or cfg.coverage_window_months)
    prior_months = row.lfl_prior_months or cfg.prior_months
    recent_span = _span(row.month, cfg.recent_months)
    evidence = _facts(
        Evidence("Cobros operativos sobre pagos operativos y deuda", inputs.get("coverage"),
                 "ratio", window, TRANSACTIONS),
        Evidence("Cobros operativos de la ventana", row.op_in_sum_6m_w, "EUR", window, TRANSACTIONS),
        Evidence("Pagos operativos y servicio de deuda de la ventana", row.outflow_sum_6m_w,
                 "EUR", window, TRANSACTIONS),
        Evidence("Cobros recientes sobre los meses previos, mismas cuentas", inputs.get("momentum"),
                 "ratio", _span(row.month, cfg.recent_months + prior_months), TRANSACTIONS),
        Evidence("Media mensual de cobros recientes, mismas cuentas",
                 recent if _known(recent) else None, "EUR", recent_span, TRANSACTIONS),
        Evidence("Media mensual de cobros de los meses previos, mismas cuentas",
                 prior if _known(prior) else None, "EUR",
                 _span(row.month, prior_months, cfg.recent_months), TRANSACTIONS),
    )
    return _result("activity", score, inputs, gates, evidence)


def pillar_debt(row: PanelRow, p: Params) -> PillarResult:
    """Debt: burden of debt service on operating inflow (anchors ``debt_burden``).

    ``burden = debt_service_sum_12m_w / op_in_sum_12m_w``; ``score = A(burden)``.
    None, first gate that applies: ``no_debt`` (no debt products and no debt
    service in the window; the weights renormalise, nothing is imputed),
    ``short_history`` (``months_in_12m_window < debt.min_months``),
    ``burden_undefined`` (``op_in_sum_12m_w`` not positive).
    """
    service, inflow = row.debt_service_sum_12m_w or 0.0, row.op_in_sum_12m_w
    months = row.months_in_12m_window or 0
    inputs: dict[str, float | None] = {
        "debt_service_12m": service,
        "op_in_12m": inflow,
        "months": float(months),
    }
    gates: list[str] = []
    score = None
    if not row.has_debt_products and not _positive(service):
        gates.append("no_debt")
    elif months < p.debt.min_months:
        gates.append("short_history")
    elif not _positive(inflow):
        gates.append("burden_undefined")
    else:
        inputs["burden"] = service / inflow
        score = p.anchors["debt_burden"](inputs["burden"])

    window = _span(row.month, months or p.debt.window_months)
    in_debt = "no_debt" not in gates
    evidence = _facts(
        Evidence("Servicio de deuda sobre cobros operativos", inputs.get("burden"), "cuota",
                 window, TRANSACTIONS),
        Evidence("Servicio de deuda de la ventana", service if in_debt else None, "EUR",
                 window, TRANSACTIONS),
        Evidence("Cobros operativos de la ventana", inflow if in_debt else None, "EUR",
                 window, TRANSACTIONS),
        Evidence("Meses observados en la ventana", months if in_debt else None,
                 "meses", window, TRANSACTIONS),
    )
    return _result("debt", score, inputs, gates, evidence)


def compute_pillars(
    row: PanelRow, p: Params, group_row: PanelRow | None = None
) -> dict[str, PillarResult]:
    """All five pillars, keyed and ordered by ``PILLAR_KEYS``. ``group_row`` is
    the group row of the same month, used only by the liquidity inheritance."""
    return {
        "liquidity": pillar_liquidity(row, p, group_row),
        "payments": pillar_payments(row, p),
        "collections": pillar_collections(row, p),
        "activity": pillar_activity(row, p),
        "debt": pillar_debt(row, p),
    }


def pillar_note(result: PillarResult, p: Params) -> str:
    """The Spanish sentence of a pillar: ``NOTE_TEMPLATES`` filled with its
    inputs when it has a score, else the text of its first blocking gate.
    Only ratios, days and shares appear, so the sentence is scale free."""
    inputs = result.inputs
    if result.score is None:
        blocking = [gate for gate in result.gates if gate not in INFORMATIVE_GATES]
        return GATE_TEXTS.get(blocking[0] if blocking else "", NOTE_TEMPLATES["unavailable"])
    if result.key == "liquidity":
        end, low = inputs.get("buffer_days_month_end"), inputs.get("buffer_days_intra_min")
        if end is None or low is None:
            return NOTE_TEMPLATES["unavailable"]
        if end <= 0:
            return NOTE_TEMPLATES["liquidity_negative"]
        name = "liquidity_inherited" if "inherited_from_group" in result.gates else "liquidity"
        low_text = _days_es(low, NOTE_MAX_DAYS) if round(low) >= 0 else f"-{_days_es(low, NOTE_MAX_DAYS)}"
        return NOTE_TEMPLATES[name].format(end=_days_es(end, NOTE_MAX_DAYS), low=low_text)
    if result.key in ("payments", "collections"):
        days = inputs.get("days_beyond_terms")
        if days is None:
            return NOTE_TEMPLATES["unavailable"]
        name = f"{result.key}_{'early' if round(days) < 0 else 'late'}"
        return NOTE_TEMPLATES[name].format(days=_days_es(days))
    if result.key == "activity":
        coverage, momentum = inputs.get("coverage"), inputs.get("momentum")
        values = dict(
            coverage=format_es(coverage, 2) if coverage is not None else "",
            momentum=format_es(momentum, 2) if momentum is not None else "",
            months=p.activity.coverage_window_months,
            recent=p.activity.recent_months,
        )
        if coverage is not None and momentum is not None:
            return NOTE_TEMPLATES["activity"].format(**values)
        if coverage is not None:
            return NOTE_TEMPLATES["activity_coverage"].format(**values)
        if momentum is not None:
            return NOTE_TEMPLATES["activity_momentum"].format(**values)
        return NOTE_TEMPLATES["unavailable"]
    burden, months = inputs.get("burden"), inputs.get("months")
    if burden is None:
        return NOTE_TEMPLATES["unavailable"]
    return NOTE_TEMPLATES["debt"].format(
        burden=format_es(burden * 100, 1), months=round(months or p.debt.window_months)
    )
