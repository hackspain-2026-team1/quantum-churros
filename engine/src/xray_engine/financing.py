"""Financing recommendations: what to offer when management levers are not enough.

Deterministic rules over the measured month, in the same style as ``actions``:
every recommendation is a delta over the measured inputs and the uplift is the
engine rescoring that month, never an estimate. A recommendation only fires
when the business fact it names is present (customers pay late, the buffer is
short, the debt service is heavy) and the financing moves the score.

- ``factoring``: customers pay late and the buffer is short -> advance the open
  AR invoices (90 % of them, the rest is the fee) and collect the cash now.
- ``confirming``: the company pays late and the buffer is short -> finance the
  open AP invoices: the provider is paid on time and the cash stays.
- ``line``: a sound business (score >= LINE_MIN_SCORE, no negative-liquidity
  cap) with a thin buffer -> a new undrawn credit line for what is missing to
  reach LINE_TARGET_BUFFER_DAYS.
- ``restructure``: the debt service is heavier than what one refinancing step
  of the action ladder can fix -> renegotiate terms down to half the service.
- ``sweep``: a company whose cash is swept or negative while the group holds
  cash -> use the group pool; the group score does not change.

Pure: no I/O, no frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping

from .actions import _cash_delta, _eur, _known, _set_attr
from .aggregate import aggregate
from .contracts import PanelRow, Params, PillarResult, ScoreParts
from .pillars import compute_pillars, format_es

MIN_UPLIFT = 0.5
FACTORING_MIN_AR_DAYS = 20.0  # customers pay this late or worse
CONFIRMING_MIN_AP_DAYS = 20.0  # the company pays this late or worse
SHORT_BUFFER_DAYS = 60.0  # a buffer under this is short
ADVANCE_SHARE = 0.90  # factoring/confirming advance: the rest is the fee
LINE_MIN_BUFFER_DAYS = 30.0  # under this a new line is worth proposing
LINE_TARGET_BUFFER_DAYS = 60.0  # the line covers up to this
LINE_MIN_SCORE = 50.0  # a new line needs a business that is not critical
BURDEN_MAX = 0.30  # debt pillar top anchor: service over inflows
RESTRUCTURE_CUT = 0.50  # renegotiating halves the service
MAX_RECOMMENDATIONS = 3


@dataclass(frozen=True)
class Financing:
    id: str  # f"{kind}", stable
    kind: str  # factoring | confirming | line | restructure | sweep
    title: str  # Spanish, imperative
    detail: str  # Spanish: the rule that fired and what it does
    amount: float | None  # EUR the instrument moves; None for restructure
    new_score: float  # aggregate() over the month with the recommendation applied
    uplift: float  # new_score - parts.score
    row_delta: Callable[[PanelRow], PanelRow] = field(default=None, compare=False, repr=False)  # type: ignore[assignment]

    @property
    def new_score_tenths(self) -> int:
        return round(min(100.0, max(0.0, self.new_score)) * 10)

    @property
    def uplift_tenths(self) -> int:
        return self.new_score_tenths - round(min(100.0, max(0.0, self.new_score - self.uplift)) * 10)


def _pillar_input(pillars: Mapping[str, PillarResult], key: str, name: str) -> float | None:
    result = pillars.get(key)
    if result is None or result.score is None:
        return None
    return result.inputs.get(name)


def _rescored(row: PanelRow, p: Params, group_row: PanelRow | None) -> ScoreParts:
    return aggregate(compute_pillars(row, p, group_row), row, p, group_row)


def _factoring(row: PanelRow, pillars: Mapping[str, PillarResult], p: Params, group_row: PanelRow | None):
    days = _pillar_input(pillars, "collections", "days_beyond_terms")
    buffer = _pillar_input(pillars, "liquidity", "buffer_days_month_end")
    open_ar = row.ar_open
    if days is None or days < FACTORING_MIN_AR_DAYS:
        return None
    if buffer is None or buffer >= SHORT_BUFFER_DAYS:
        return None
    if not _known(row.cash_month_end) or not open_ar or open_ar <= 0:
        return None
    advance = open_ar * ADVANCE_SHARE
    base = _parts_score(pillars, row, p, group_row)
    delta = lambda row_: _cash_delta(row_, advance)
    parts = _rescored(delta(row), p, group_row)
    if parts.score - base < MIN_UPLIFT:
        return None
    return Financing(
        id="factoring",
        kind="factoring",
        title=f"Anticipa {format_es(open_ar * ADVANCE_SHARE, 0)} de facturas de clientes",
        detail=(
            f"Tus clientes pagan de media {format_es(days, 0)} días tarde y tu colchón está en "
            f"{format_es(buffer, 0)} días. Adelantar el {int(ADVANCE_SHARE * 100)} % de las facturas "
            f"abiertas ({_eur(open_ar)}) te da {_eur(advance)} de caja hoy; la comisión la paga el "
            "cliente que paga tarde, no el score: el motor ya recalculó el número con esa caja."
        ),
        amount=advance,
        new_score=parts.score,
        uplift=parts.score - base,
        row_delta=delta,
    )


def _parts_score(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params, group_row: PanelRow | None
) -> float:
    return aggregate(pillars, row, p, group_row).score


def _confirming(row: PanelRow, pillars: Mapping[str, PillarResult], p: Params, group_row: PanelRow | None):
    days = _pillar_input(pillars, "payments", "days_beyond_terms")
    buffer = _pillar_input(pillars, "liquidity", "buffer_days_month_end")
    open_ap = row.ap_open
    if days is None or days < CONFIRMING_MIN_AP_DAYS:
        return None
    if buffer is None or buffer >= SHORT_BUFFER_DAYS:
        return None
    if not _known(row.cash_month_end) or not open_ap or open_ap <= 0:
        return None
    financed = open_ap * ADVANCE_SHARE
    # The provider is paid on time and the company keeps the cash: its own delay
    # falls back by one bounded step, the rest is what it actually achieves.
    new_days = max(0.0, days - 30.0)
    base = _parts_score(pillars, row, p, group_row)

    def delta(row_: PanelRow) -> PanelRow:
        return _cash_delta(_set_attr("ap_days_beyond_terms", new_days)(row_), financed)

    parts = _rescored(delta(row), p, group_row)
    if parts.score - base < MIN_UPLIFT:
        return None
    return Financing(
        id="confirming",
        kind="confirming",
        title=f"Financia {format_es(open_ap * ADVANCE_SHARE, 0)} de pagos a proveedores",
        detail=(
            f"Hoy pagas de media {format_es(days, 0)} días tarde y tu colchón está en "
            f"{format_es(buffer, 0)} días. Con confirming tus proveedores cobran al vencimiento y "
            f"vos conservas {_eur(financed)} de caja; el score mostrado ya cuenta con ello."
        ),
        amount=financed,
        new_score=parts.score,
        uplift=parts.score - base,
        row_delta=delta,
    )


def _line(row: PanelRow, pillars: Mapping[str, PillarResult], parts: ScoreParts, p: Params, group_row: PanelRow | None):
    buffer = _pillar_input(pillars, "liquidity", "buffer_days_month_end")
    monthly = _pillar_input(pillars, "liquidity", "monthly_outflow")
    if buffer is None or buffer >= LINE_MIN_BUFFER_DAYS:
        return None
    if not monthly or monthly <= 0:
        return None
    if parts.score < LINE_MIN_SCORE or "negative_liquidity" in parts.caps_fired:
        return None
    if not _known(row.headroom) and not _known(row.headroom_at_min):
        return None
    amount = max(0.0, LINE_TARGET_BUFFER_DAYS - buffer) * monthly / p.liquidity.days_per_month

    def delta(row_: PanelRow) -> PanelRow:
        changes = {}
        if _known(row_.headroom):
            changes["headroom"] = (row_.headroom or 0.0) + amount
        if _known(row_.headroom_at_min):
            changes["headroom_at_min"] = (row_.headroom_at_min or 0.0) + amount
        return replace(row_, **changes) if changes else row_

    parts_new = _rescored(delta(row), p, group_row)
    if parts_new.score - parts.score < MIN_UPLIFT:
        return None
    return Financing(
        id="line",
        kind="line",
        title=f"Abre una póliza de {_eur(amount)} sin disponer",
        detail=(
            f"Tu colchón cubre {format_es(buffer, 0)} días y tu negocio no está en crítico. Una línea "
            f"nueva de {_eur(amount)} sin disponer te deja en {format_es(LINE_TARGET_BUFFER_DAYS, 0)} días "
            "de pagos cubiertos sin gastar un euro hasta usarla: el disponible ya cuenta en tu score."
        ),
        amount=amount,
        new_score=parts_new.score,
        uplift=parts_new.score - parts.score,
        row_delta=delta,
    )


def _restructure(row: PanelRow, pillars: Mapping[str, PillarResult], parts: ScoreParts, p: Params, group_row: PanelRow | None):
    burden = _pillar_input(pillars, "debt", "burden")
    inflow = _pillar_input(pillars, "debt", "op_in_12m")
    if burden is None or not inflow or inflow <= 0:
        return None
    # one bounded refinancing step (-30 %) must not be enough for this to be restructuring
    if burden * 0.70 <= BURDEN_MAX:
        return None
    goal = burden * RESTRUCTURE_CUT
    service_now, service_new = burden * inflow, goal * inflow
    monthly_freed = (service_now - service_new) / 12.0

    def delta(row_: PanelRow) -> PanelRow:
        return _cash_delta(_set_attr("debt_service_sum_12m_w", service_new)(row_), monthly_freed)

    parts_new = _rescored(delta(row), p, group_row)
    if parts_new.score - parts.score < MIN_UPLIFT:
        return None
    return Financing(
        id="restructure",
        kind="restructure",
        title=f"Renegocia la deuda: del {format_es(burden * 100, 1)} % al {format_es(goal * 100, 1)} % de tus cobros",
        detail=(
            f"El servicio de la deuda consume el {format_es(burden * 100, 1)} % de lo que cobras; ni "
            "refinanciar una vez alcanza. Renegociar plazos y condiciones hasta la mitad libera "
            f"{_eur(monthly_freed)} de caja al mes y sube el pilar de deuda: el score mostrado ya lo incluye."
        ),
        amount=None,
        new_score=parts_new.score,
        uplift=parts_new.score - parts.score,
        row_delta=delta,
    )


def _sweep(row: PanelRow, pillars: Mapping[str, PillarResult], parts: ScoreParts, p: Params, group_row: PanelRow | None):
    if group_row is None or row.entity_kind != "company":
        return None
    liquidity = pillars.get("liquidity")
    if liquidity is not None and "inherited_from_group" in liquidity.gates:
        return None  # already scored on the group's cash: no own lever to pull
    cash = row.cash_month_end
    if not _known(cash) or cash >= 0:
        return None
    if not _known(group_row.cash_month_end) or group_row.cash_month_end <= 0:
        return None
    amount = -cash
    if group_row.cash_month_end < amount:
        return None  # the pool cannot cover it all
    delta = lambda row_: _cash_delta(row_, amount)
    parts_new = _rescored(delta(row), p, group_row)
    if parts_new.score - parts.score < MIN_UPLIFT:
        return None
    return Financing(
        id="sweep",
        kind="sweep",
        title=f"Trae {_eur(amount)} del cash pooling del grupo",
        detail=(
            f"Tu caja cierra en {_eur(cash)} y el grupo tiene caja de sobra. Un barrido interno de "
            f"{_eur(amount)} te deja el mes en cero y arregla tu liquidez; el score del grupo no cambia, "
            "porque es la misma caja consolidada."
        ),
        amount=amount,
        new_score=parts_new.score,
        uplift=parts_new.score - parts.score,
        row_delta=delta,
    )


def recommendations(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    params: Params,
    group_row: PanelRow | None = None,
) -> list[Financing]:
    """The financing options of one entity-month, best uplift first, at most 3."""
    if parts.abstained or not parts.feed_live or parts.carried_from is not None:
        return []
    found = [
        item
        for item in (
            _factoring(row, pillars, params, group_row),
            _confirming(row, pillars, params, group_row),
            _line(row, pillars, parts, params, group_row),
            _restructure(row, pillars, parts, params, group_row),
            _sweep(row, pillars, parts, params, group_row),
        )
        if item is not None
    ]
    found.sort(key=lambda item: -item.uplift)
    return found[:MAX_RECOMMENDATIONS]
