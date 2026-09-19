"""Suggested actions with their expected score uplift. Pure: no I/O, no frames.

For every available pillar below ``TARGET_CEILING`` a realistic target is set
(the next anchor step of its table, at most ``MAX_STEP`` pillar points, never
above ``TARGET_CEILING``), the anchor table is inverted to the input that gives
that score (days, ratio, share) and turned into money with the facts of the
row. The uplift is never estimated: the score is recomputed by ``aggregate``
with the pillar replaced, so the penalty and the caps react as they would.
Abstained, stale and carried months give no actions; an inherited liquidity is
not the company's lever and is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .aggregate import aggregate
from .contracts import PILLAR_KEYS, Anchors, PanelRow, Params, PillarResult, ScoreParts
from .pillars import format_es, liquidity_anchors

TARGET_CEILING = 80.0  # a pillar at or above it needs no action
MAX_STEP = 25.0  # pillar points one action may promise
MIN_UPLIFT = 0.5  # score points; smaller actions are not worth showing
MAX_ACTIONS = 4
EFFORT_STEPS: tuple[tuple[float, str], ...] = ((10.0, "bajo"), (20.0, "medio"))
EFFORT_HIGH = "alto"
_EPS = 1e-9


@dataclass(frozen=True)
class Action:
    id: str  # f"{pillar}-{kind}", stable
    pillar: str
    title: str  # Spanish, imperative
    detail: str  # Spanish: the lever and why it moves the score
    current: float
    target: float
    unit: str  # "días" | "ratio" | "%"
    pillar_target: float  # pillar score the action reaches
    new_score: float  # aggregate() with the pillar at pillar_target
    uplift: float  # new_score - parts.score
    effort: str

    @property
    def uplift_tenths(self) -> int:
        return self.new_score_tenths - _tenths(self.new_score - self.uplift)

    @property
    def new_score_tenths(self) -> int:
        return _tenths(self.new_score)


@dataclass(frozen=True)
class ActionPlan:
    actions: tuple[Action, ...]
    combined_score: float  # every suggested pillar target applied at once
    combined_uplift: float

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


def _liquidity(result: PillarResult, row: PanelRow, p: Params) -> tuple[float, dict] | None:
    inputs = result.inputs
    end, low = inputs.get("buffer_days_month_end"), inputs.get("buffer_days_intra_min")
    monthly = inputs.get("monthly_outflow")
    if end is None or low is None or not monthly or monthly <= 0:
        return None
    table, _ = liquidity_anchors(row, p)
    cfg = p.liquidity

    def blended(extra: float) -> float:
        return cfg.month_end_weight * table(end + extra) + cfg.intra_min_weight * table(low + extra)

    span = max(table.points[-1][0] - min(end, low), 0.0)
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
    score = min(target, blended(extra))
    money = extra * monthly / cfg.days_per_month
    shown_end = max(0.0, end)
    return score, {
        "kind": "buffer",
        "title": f"Sube tu colchón de caja de {round(shown_end)} a {_days(end + extra)}",
        "detail": (
            f"Necesitas unos {_eur(money)} más entre caja y líneas de crédito sin disponer: "
            f"son {_days(extra)} más de pagos cubiertos, a fin de mes y en el peor día del mes. "
            "El colchón de liquidez es lo que más pesa cuando la nota es baja."
        ),
        "current": end,
        "target": end + extra,
        "unit": "días",
    }


def _punctuality(result: PillarResult, p: Params) -> tuple[float, dict] | None:
    days = result.inputs.get("days_beyond_terms")
    if days is None:
        return None
    table = p.anchors[result.key]
    target = step_target(result.score, table)
    goal = invert(table, target, days) if target is not None else None
    if goal is None or goal >= days - _EPS:
        return None
    gain = days - goal
    if result.key == "payments":
        title = (
            f"Reduce el retraso medio con proveedores de {round(days)} a {_days(goal)}"
            if round(goal) > 0 else f"Paga a tus proveedores {_days(gain)} antes"
        )
        detail = (
            f"Hoy pagas de media {_days(days)} {'después' if days >= 0 else 'antes'} del vencimiento, "
            f"ponderado por importe. Adelantar {_days(gain)} los pagos, empezando por las facturas "
            "grandes, mejora la puntualidad y puede levantar el tope que limita la nota."
        )
        kind = "punctuality"
    else:
        title = f"Cobra a tus clientes {_days(gain)} antes"
        detail = (
            f"Tus clientes pagan de media {_days(days)} {'después' if days >= 0 else 'antes'} del vencimiento, "
            f"ponderado por importe. {'Bajar a ' + _days(goal) + ' de retraso' if round(goal) > 0 else 'Cobrar al vencimiento'} con recordatorios, anticipo de facturas o "
            "domiciliación mejora el pilar de cobros y acorta el ciclo de caja."
        )
        kind = "speed"
    return target, {"kind": kind, "title": title, "detail": detail, "current": days, "target": goal, "unit": "días"}


def _activity(result: PillarResult, row: PanelRow, p: Params) -> tuple[float, dict] | None:
    inputs = result.inputs
    coverage, sub = inputs.get("coverage"), inputs.get("score_coverage")
    inflow, outflow = inputs.get("op_in_6m"), inputs.get("outflow_6m")
    if coverage is None or sub is None or inflow is None or not outflow or outflow <= 0:
        return None
    table = p.anchors["activity_coverage"]
    momentum = inputs.get("score_momentum")
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
    score = sub_target if momentum is None else (sub_target + momentum) / 2
    months = max(1, row.months_in_6m_window or p.activity.coverage_window_months)
    more_in = (goal * outflow - inflow) / months
    less_out = (outflow - inflow / goal) / months
    return score, {
        "kind": "coverage",
        "title": (
            f"Lleva la cobertura de tus pagos de {format_es(coverage, 2)} a {format_es(goal, 2)} veces"
        ),
        "detail": (
            f"Tus cobros operativos cubren {format_es(coverage, 2)} veces tus pagos. Llegar a "
            f"{format_es(goal, 2)} supone unos {_eur(more_in)} más de cobros al mes o "
            f"{_eur(less_out)} menos de pagos al mes. Un negocio que cubre sus salidas con ventas sostiene la nota."
        ),
        "current": coverage,
        "target": goal,
        "unit": "ratio",
    }


def _debt(result: PillarResult, p: Params) -> tuple[float, dict] | None:
    inputs = result.inputs
    burden, inflow = inputs.get("burden"), inputs.get("op_in_12m")
    if burden is None or not inflow or inflow <= 0:
        return None
    table = p.anchors["debt_burden"]
    target = step_target(result.score, table)
    goal = invert(table, target, burden) if target is not None else None
    if goal is None or goal >= burden - _EPS:
        return None
    months = max(1.0, inputs.get("months") or float(p.debt.window_months))
    yearly = (burden - goal) * inflow * 12.0 / months
    return target, {
        "kind": "burden",
        "title": (
            f"Baja el peso de tu deuda del {format_es(burden * 100, 1)} % al "
            f"{format_es(goal * 100, 1)} % de tus cobros"
        ),
        "detail": (
            f"El servicio de la deuda consume el {format_es(burden * 100, 1)} % de lo que cobras. "
            f"Pagar unos {_eur(yearly)} menos al año en cuotas e intereses (refinanciando a más plazo "
            "o amortizando lo más caro) libera caja y mejora el pilar de deuda."
        ),
        "current": burden * 100,
        "target": goal * 100,
        "unit": "%",
    }


def _proposal(result: PillarResult, row: PanelRow, p: Params, group_row: PanelRow | None):
    if result.key == "liquidity":
        if "inherited_from_group" in result.gates:
            return None
        return _liquidity(result, row, p)
    if result.key in ("payments", "collections"):
        return _punctuality(result, p)
    if result.key == "activity":
        return _activity(result, row, p)
    return _debt(result, p)


def plan_actions(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    params: Params,
    group_row: PanelRow | None = None,
) -> ActionPlan:
    """Actions of one entity-month and the score with all of them applied.

    Every ``uplift`` is ``aggregate(pillars with one score replaced).score -
    parts.score``; ``combined_score`` replaces every suggested pillar at once.
    Kept: uplift ``>= MIN_UPLIFT``, sorted by uplift (ties in ``PILLAR_KEYS``
    order), at most ``MAX_ACTIONS``. Empty on abstained, stale or carried months.
    """
    empty = ActionPlan((), parts.score, 0.0)
    if parts.abstained or not parts.feed_live or parts.carried_from is not None:
        return empty
    found: list[Action] = []
    for key in PILLAR_KEYS:
        result = pillars.get(key)
        if result is None or result.score is None or result.score >= TARGET_CEILING:
            continue
        proposal = _proposal(result, row, params, group_row)
        if proposal is None:
            continue
        pillar_target, text = proposal
        if pillar_target <= result.score + _EPS:
            continue
        changed = {**pillars, key: replace(result, score=pillar_target)}
        new_score = aggregate(changed, row, params, group_row).score
        uplift = new_score - parts.score
        if uplift < MIN_UPLIFT:
            continue
        found.append(
            Action(
                id=f"{key}-{text['kind']}", pillar=key, title=text["title"], detail=text["detail"],
                current=text["current"], target=text["target"], unit=text["unit"],
                pillar_target=pillar_target, new_score=new_score, uplift=uplift,
                effort=_effort(pillar_target - result.score),
            )
        )
    found.sort(key=lambda action: (-action.uplift, PILLAR_KEYS.index(action.pillar)))
    kept = tuple(found[:MAX_ACTIONS])
    if not kept:
        return empty
    changed = dict(pillars)
    for action in kept:
        changed[action.pillar] = replace(pillars[action.pillar], score=action.pillar_target)
    combined = aggregate(changed, row, params, group_row).score
    return ActionPlan(kept, combined, combined - parts.score)


def suggest_actions(
    row: PanelRow,
    pillars: Mapping[str, PillarResult],
    parts: ScoreParts,
    params: Params,
    group_row: PanelRow | None = None,
) -> list[Action]:
    return list(plan_actions(row, pillars, parts, params, group_row).actions)
