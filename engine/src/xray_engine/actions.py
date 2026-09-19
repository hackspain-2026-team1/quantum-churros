"""Suggested actions with their expected score uplift. Pure: no I/O, no frames.

Each action is a delta over the measured inputs of the month: the row is
transformed, every pillar is recomputed and ``aggregate`` reacts with its
penalty and caps. The uplift is the score the engine gives the modified month,
never an estimate, so a lever that spends cash (paying suppliers earlier) pays
its liquidity cost and a lever that brings cash (collecting earlier, lighter
debt service) gets its liquidity reward, including the negative-liquidity cap
when a lever flips the month-end sign.

Every lever is bounded to what a finance team can plausibly move in about two
quarters (see ``MAX_*``). The plan is a ladder: stage 1 acts on the current
month, each next stage acts on the month the previous one produced, up to
``MAX_STAGES``, so the product can show the whole path to the best achievable
score. Abstained, stale and carried months give no actions; an inherited
liquidity is not the company's lever and is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping

from .aggregate import aggregate
from .contracts import PILLAR_KEYS, Anchors, PanelRow, Params, PillarResult, ScoreParts
from .pillars import compute_pillars, format_es, liquidity_anchors

TARGET_CEILING = 80.0  # a pillar at or above it needs no action
MAX_STEP = 25.0  # pillar points one action may promise (kept: the anchor-step search)
MIN_UPLIFT = 0.5  # score points; smaller actions are not worth showing
MAX_ACTIONS = 4
MAX_STAGES = 3
# What a finance team can plausibly move in about two quarters. A lever never asks for
# more: the action promises the score the engine gives the bounded lever, not the anchor.
MAX_EXTRA_BUFFER_DAYS = 30.0  # one more month of payments covered
MAX_DAYS_GAIN = 30.0  # days of delay recovered with suppliers or customers
MAX_COVERAGE_GAIN = 0.15  # relative rise of operating inflows over outflows
MAX_BURDEN_CUT = 0.30  # relative cut of debt service, what a refinancing gives
EFFORT_STEPS: tuple[tuple[float, str], ...] = ((10.0, "bajo"), (20.0, "medio"))
EFFORT_HIGH = "alto"
_EPS = 1e-9

RowDelta = Callable[[PanelRow], PanelRow]


@dataclass(frozen=True)
class Action:
    id: str  # f"{pillar}-{kind}", stable
    pillar: str
    title: str  # Spanish, imperative
    detail: str  # Spanish: the lever and why it moves the score
    current: float
    target: float
    unit: str  # "días" | "ratio" | "%"
    pillar_target: float  # pillar score the lever reaches
    new_score: float  # aggregate() over the month with the lever applied
    uplift: float  # new_score - parts.score
    effort: str
    row_delta: RowDelta = field(compare=False, repr=False)  # the lever; ladder and tests

    @property
    def uplift_tenths(self) -> int:
        return self.new_score_tenths - _tenths(self.new_score - self.uplift)

    @property
    def new_score_tenths(self) -> int:
        return _tenths(self.new_score)


@dataclass(frozen=True)
class Stage:
    number: int
    actions: tuple[Action, ...]
    score: float  # score after this stage's actions
    uplift: float  # cumulative: stage.score minus the original score


@dataclass(frozen=True)
class ActionPlan:
    actions: tuple[Action, ...]  # stage 1: the contract that existed
    combined_score: float  # every stage-1 lever applied at once
    combined_uplift: float
    stages: tuple[Stage, ...] = ()
    max_score: float | None = None  # score after the last stage
    max_uplift: float | None = None  # max_score minus the original score

    @property
    def combined_score_tenths(self) -> int:
        return _tenths(self.combined_score)

    @property
    def combined_uplift_tenths(self) -> int:
        return self.combined_score_tenths - _tenths(self.combined_score - self.combined_uplift)


def _tenths(score: float) -> int:
    return round(min(100.0, max(0.0, score)) * 10)


def _eur(value: float) -> str:
    text = f"{abs(round(value)):,}".replace(",", ".")
    return f"{text} EUR"


def _days(value: float) -> str:
    count = abs(round(value))
    return f"{count} día" if count == 1 else f"{count} días"


def _known(value: float | None) -> bool:
    return value is not None


def _effort(gap: float) -> str:
    for limit, label in EFFORT_STEPS:
        if gap <= limit + _EPS:
            return label
    return EFFORT_HIGH


def step_target(score: float, table: Anchors, ceiling: float = TARGET_CEILING) -> float | None:
    """Next anchor level above ``score``, at most ``MAX_STEP`` points up and
    never above ``ceiling`` nor the top of the table. None when nothing is left."""
    top = min(ceiling, max(y for _, y in table.points))
    levels = sorted(y for _, y in table.points if y > score + _EPS)
    target = min(levels[0] if levels else top, score + MAX_STEP, top)
    return target if target > score + _EPS else None


def invert(table: Anchors, target: float, near: float) -> float | None:
    """The x closest to ``near`` with ``table(x) == target``; None when the
    table never reaches it."""
    found: list[float] = []
    for (x0, y0), (x1, y1) in zip(table.points, table.points[1:]):
        if y0 != y1 and min(y0, y1) - _EPS <= target <= max(y0, y1) + _EPS:
            found.append(x0 + (x1 - x0) * (target - y0) / (y1 - y0))
    return min(found, key=lambda x: (abs(x - near), x)) if found else None


def _cash_delta(row: PanelRow, money: float) -> PanelRow:
    """Shift both cash figures by ``money`` and keep the negative-liquidity
    month count consistent with the month-end sign the cap reads."""
    if abs(money) <= _EPS:
        return row
    changes: dict[str, float | int] = {}
    if _known(row.cash_month_end):
        end_now = row.cash_month_end + money
        headroom = row.headroom or 0.0
        end_was_negative = row.cash_month_end + headroom < 0
        end_is_negative = end_now + headroom < 0
        if end_was_negative != end_is_negative:
            changes["neg_liquidity_months_6m"] = (row.neg_liquidity_months_6m or 0) + (
                -1 if end_was_negative else 1
            )
        changes["cash_month_end"] = end_now
    if _known(row.cash_intra_month_min):
        changes["cash_intra_month_min"] = row.cash_intra_month_min + money
    return replace(row, **changes) if changes else row


def _set_attr(name: str, value: float) -> RowDelta:
    return lambda row: replace(row, **{name: value})


def _buffer(result: PillarResult, row: PanelRow, p: Params) -> tuple[RowDelta, dict] | None:
    inputs = result.inputs
    end, low = inputs.get("buffer_days_month_end"), inputs.get("buffer_days_intra_min")
    monthly = inputs.get("monthly_outflow")
    if end is None or low is None or not monthly or monthly <= 0:
        return None
    table, _ = liquidity_anchors(row, p)
    cfg = p.liquidity

    def blended(extra: float) -> float:
        return cfg.month_end_weight * table(end + extra) + cfg.intra_min_weight * table(low + extra)

    span = min(max(table.points[-1][0] - min(end, low), 0.0), MAX_EXTRA_BUFFER_DAYS)
    target = step_target(result.score, table, min(TARGET_CEILING, blended(span)))
    if target is None:
        return None
    lo, hi = 0.0, span  # same extra days on both buffers: cash added stays all month
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if blended(mid) >= target else (mid, hi)
    extra = hi
    if extra <= _EPS:
        return None
    money = extra * monthly / cfg.days_per_month
    shown_end = max(0.0, end)
    return lambda row_: _cash_delta(row_, money), {
        "kind": "buffer",
        "title": f"Sube tu colchón de caja de {round(shown_end)} a {_days(end + extra)}",
        "detail": (
            f"Necesitas unos {_eur(money)} de caja nueva, de capital o financiación a largo plazo: "
            f"son {_days(extra)} más de pagos cubiertos, a fin de mes y en el peor día del mes. "
            "Una póliza de crédito no sirve aquí: su disponible ya está contado en el colchón."
        ),
        "current": end,
        "target": end + extra,
        "unit": "días",
    }


def _punctuality(result: PillarResult, row: PanelRow, p: Params) -> tuple[RowDelta, dict] | None:
    key = result.key
    side = "ap" if key == "payments" else "ar"
    days = result.inputs.get("days_beyond_terms")
    if days is None:
        return None
    table = p.anchors[key]
    target = step_target(result.score, table)
    goal = invert(table, target, days) if target is not None else None
    if goal is None or goal >= days - _EPS:
        return None
    if days - goal > MAX_DAYS_GAIN:
        goal = days - MAX_DAYS_GAIN
    gain = days - goal
    # The as-of cohort covers the invoices due in the last 90 days, so a month of
    # payments is about a third of it: paying (or collecting) G days earlier is a
    # one-time cash move of cohort * G / 90.
    cohort = getattr(row, f"{side}_amount") or 0.0
    cash = cohort * gain / 90.0 if cohort > 0 else 0.0
    if key == "payments":
        delta: RowDelta = lambda row_: _cash_delta(_set_attr("ap_days_beyond_terms", goal)(row_), -cash)
        title = (
            f"Reduce el retraso medio con proveedores de {round(days)} a {_days(goal)}"
            if round(goal) > 0 else f"Paga a tus proveedores {_days(gain)} antes"
        )
        detail = (
            f"Hoy pagas de media {_days(days)} {'después' if days >= 0 else 'antes'} del vencimiento, "
            f"ponderado por importe. Adelantar {_days(gain)} los pagos, empezando por las facturas "
            f"grandes, cuesta unos {_eur(cash)} de caja este mes: el efecto en tu colchón y en la nota "
            "final ya está descontado."
        )
        kind = "punctuality"
    else:
        delta = lambda row_: _cash_delta(_set_attr("ar_days_beyond_terms", goal)(row_), cash)
        title = f"Cobra a tus clientes {_days(gain)} antes"
        detail = (
            f"Tus clientes pagan de media {_days(days)} {'después' if days >= 0 else 'antes'} del vencimiento, "
            f"ponderado por importe. {'Bajar a ' + _days(goal) + ' de retraso' if round(goal) > 0 else 'Cobrar al vencimiento'} "
            f"con recordatorios o anticipo de facturas te da unos {_eur(cash)} de caja este mes, ya sumados "
            "al resultado, y acorta el ciclo de caja."
        )
        kind = "speed"
    return delta, {"kind": kind, "title": title, "detail": detail, "current": days, "target": goal, "unit": "días"}


def _coverage(result: PillarResult, row: PanelRow, p: Params) -> tuple[RowDelta, dict] | None:
    inputs = result.inputs
    coverage, sub = inputs.get("coverage"), inputs.get("score_coverage")
    inflow = inputs.get("op_in_6m")
    momentum = inputs.get("score_momentum")
    if coverage is None or sub is None or inflow is None:
        return None
    table = p.anchors["activity_coverage"]
    target = step_target(result.score, table if momentum is None else Anchors(((0.0, 0.0), (1.0, 100.0))))
    if target is None:
        return None
    top = max(y for _, y in table.points)
    sub_target = min(top, target if momentum is None else 2 * target - momentum)
    if sub_target <= sub + _EPS:
        return None
    goal = invert(table, sub_target, coverage)
    if goal is None or goal <= coverage + _EPS:
        return None
    if goal > coverage * (1 + MAX_COVERAGE_GAIN):
        goal = coverage * (1 + MAX_COVERAGE_GAIN)
    factor = goal / coverage
    # More inflows: the 6m and 12m operating sums and the like-for-like recent
    # mean all grow by the same factor, and one month of the extra inflow lands
    # in cash. The lighter burden (same debt service over more inflows) is the
    # engine's own reaction, not a promise.
    monthly_gain = (factor - 1.0) * inflow / 6.0
    changes = {
        name: value * factor
        for name, value in (
            ("op_in_sum_6m_w", row.op_in_sum_6m_w),
            ("op_in_sum_12m_w", row.op_in_sum_12m_w),
            ("op_in_lfl_recent_mean", row.op_in_lfl_recent_mean),
        )
        if _known(value)
    }
    return lambda row_: _cash_delta(replace(row_, **changes), monthly_gain), {
        "kind": "coverage",
        "title": (
            f"Lleva la cobertura de tus pagos de {format_es(coverage, 2)} a {format_es(goal, 2)} veces"
        ),
        "detail": (
            f"Tus cobros operativos cubren {format_es(coverage, 2)} veces tus pagos. Llegar a "
            f"{format_es(goal, 2)} supone unos {_eur(monthly_gain)} más de cobros al mes; "
            "también alivia el peso de tu deuda y suma caja, y todo eso ya está en el resultado."
        ),
        "current": coverage,
        "target": goal,
        "unit": "ratio",
    }


def _debt(result: PillarResult, p: Params) -> tuple[RowDelta, dict] | None:
    inputs = result.inputs
    burden, inflow = inputs.get("burden"), inputs.get("op_in_12m")
    if burden is None or not inflow or inflow <= 0:
        return None
    table = p.anchors["debt_burden"]
    target = step_target(result.score, table)
    goal = invert(table, target, burden) if target is not None else None
    if goal is None or goal >= burden - _EPS:
        return None
    if goal < burden * (1 - MAX_BURDEN_CUT):
        goal = burden * (1 - MAX_BURDEN_CUT)
    service_now, service_new = burden * inflow, goal * inflow
    monthly_freed = (service_now - service_new) / 12.0
    delta = lambda row_: _cash_delta(
        _set_attr("debt_service_sum_12m_w", service_new)(row_), monthly_freed
    )
    return delta, {
        "kind": "burden",
        "title": (
            f"Baja el peso de tu deuda del {format_es(burden * 100, 1)} % al "
            f"{format_es(goal * 100, 1)} % de tus cobros"
        ),
        "detail": (
            f"El servicio de la deuda consume el {format_es(burden * 100, 1)} % de lo que cobras. "
            f"Refinanciar a más plazo o amortizar lo más caro libera unos {_eur(monthly_freed)} de caja "
            "al mes: el pilar de deuda y el colchón suben, y todo eso ya está en el resultado."
        ),
        "current": burden * 100,
        "target": goal * 100,
        "unit": "%",
    }


def _propose(result: PillarResult, row: PanelRow, p: Params) -> tuple[RowDelta, dict] | None:
    if result.key == "liquidity":
        if "inherited_from_group" in result.gates:
            return None
        return _buffer(result, row, p)
    if result.key in ("payments", "collections"):
        return _punctuality(result, row, p)
    if result.key == "activity":
        return _coverage(result, row, p)
    return _debt(result, p)


def _apply(row: PanelRow, deltas: tuple[RowDelta, ...]) -> PanelRow:
    for delta in deltas:
        row = delta(row)
    return row


def _candidates(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    p: Params,
    group_row: PanelRow | None,
) -> list[tuple[Action, RowDelta]]:
    """Every lever worth showing on this month: the delta, the row it produces
    and the full recomputed score. Sorted by uplift, at most ``MAX_ACTIONS``."""
    found: list[tuple[Action, RowDelta]] = []
    for key in PILLAR_KEYS:
        result = pillars.get(key)
        if result is None or result.score is None or result.score >= TARGET_CEILING:
            continue
        proposal = _propose(result, row, p)
        if proposal is None:
            continue
        delta, text = proposal
        new_row = delta(row)
        new_pillars = compute_pillars(new_row, p, group_row)
        new_parts = aggregate(new_pillars, new_row, p, group_row)
        uplift = new_parts.score - parts.score
        pillar_target = new_pillars[key].score
        if pillar_target is None or uplift < MIN_UPLIFT:
            continue
        found.append(
            (
                Action(
                    id=f"{key}-{text['kind']}",
                    pillar=key,
                    title=text["title"],
                    detail=text["detail"],
                    current=text["current"],
                    target=text["target"],
                    unit=text["unit"],
                    pillar_target=pillar_target,
                    new_score=new_parts.score,
                    uplift=uplift,
                    effort=_effort(pillar_target - (result.score or 0.0)),
                    row_delta=delta,
                ),
                delta,
            )
        )
    found.sort(key=lambda pair: (-pair[0].uplift, PILLAR_KEYS.index(pair[0].pillar)))
    return found[:MAX_ACTIONS]


def plan_actions(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    params: Params,
    group_row: PanelRow | None = None,
) -> ActionPlan:
    """Actions of one entity-month and the score with all of them applied.

    Every ``uplift`` is ``aggregate(compute_pillars(lever applied)).score -
    parts.score``; ``combined_score`` applies every stage-1 lever at once. The
    ladder re-scores the month each stage produces, up to ``MAX_STAGES``, so
    ``max_score`` is the best the bounded levers can reach. Empty on abstained,
    stale or carried months.
    """
    if parts.abstained or not parts.feed_live or parts.carried_from is not None:
        return ActionPlan((), parts.score, 0.0, max_score=parts.score, max_uplift=0.0)

    def rescore(state: PanelRow) -> tuple[Mapping[str, PillarResult], ScoreParts]:
        new_pillars = compute_pillars(state, params, group_row)
        return new_pillars, aggregate(new_pillars, state, params, group_row)

    first = _candidates(row, pillars, parts, params, group_row)
    if not first:
        return ActionPlan((), parts.score, 0.0, max_score=parts.score, max_uplift=0.0)
    first_actions = tuple(action for action, _ in first)
    combined_row = _apply(row, tuple(delta for _, delta in first))
    combined_score = rescore(combined_row)[1].score

    stages: list[Stage] = []
    state, state_parts = row, parts
    kept: tuple[Action, ...] = first_actions
    deltas: tuple[RowDelta, ...] = tuple(delta for _, delta in first)
    while kept and len(stages) < MAX_STAGES:
        end_row = _apply(state, deltas)
        end_score = rescore(end_row)[1].score
        stages.append(
            Stage(len(stages) + 1, kept, end_score, end_score - parts.score)
        )
        state = end_row
        state_pillars, state_parts = rescore(state)
        next_found = _candidates(state, state_pillars, state_parts, params, group_row)
        if not next_found:
            break
        kept = tuple(action for action, _ in next_found)
        deltas = tuple(delta for _, delta in next_found)

    last = stages[-1]
    return ActionPlan(
        first_actions,
        combined_score,
        combined_score - parts.score,
        stages=tuple(stages),
        max_score=last.score,
        max_uplift=last.uplift,
    )


def suggest_actions(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    params: Params,
    group_row: PanelRow | None = None,
) -> list[Action]:
    return list(plan_actions(row, pillars, parts, params, group_row).actions)
