"""A stale month shows the last live score, with the explanation that produced it."""

from __future__ import annotations

import random
from dataclasses import fields, replace
from datetime import date

import pytest
from xray_engine import scoring
from xray_engine.contracts import (
    CARRIED_GATE,
    PILLAR_KEYS,
    DeltaParts,
    EntityMonth,
    PanelRow,
    PillarResult,
    ScoreParts,
    Trajectory,
)
from xray_engine.scoring import CARRIED_FIELDS, carried_pillars, carry_forward, score_entity

TOL = 1e-9
START = date(2025, 1, 1)


def _explained(parts: ScoreParts) -> float:
    return parts.base + sum(parts.contributions.values()) - parts.penalty - parts.cap_adjustment


def test_the_explanation_block_is_copied_whole(score_parts, params) -> None:
    live = score_parts.live(START, 47.0, params, penalty=3.0, cap_adjustment=4.0, level_weighted=54.0,
                            caps_fired=("negative_liquidity",), flags=("debt_snapshot",), size_band="small")
    live = replace(live, contributions={key: value + 3.5 for key, value in live.contributions.items()})
    assert live.score == pytest.approx(_explained(live), abs=TOL)
    own = score_parts.stale(date(2025, 3, 1), 81.0, params, months_observed=14, size_band="medium")
    carried = carry_forward(own, live)

    for name in CARRIED_FIELDS:
        assert getattr(carried, name) == getattr(live, name), name
    kept = {item.name for item in fields(ScoreParts)} - set(CARRIED_FIELDS) - {"carried_from"}
    for name in kept:
        assert getattr(carried, name) == getattr(own, name), name
    assert carried.carried_from == live.month and carried.month == date(2025, 3, 1)
    # the number on screen is the last live one; the own level stays visible
    assert (carried.score, carried.level, carried.band) == (47.0, 81.0, live.band)
    assert not carried.feed_live and carried.abstained and carried.abstain_reason == "stale_feed"
    assert "stale_feed" in carried.flags and carried.caps_fired == ("negative_liquidity",)
    # both identities survive, because nothing was mixed
    assert carried.score == pytest.approx(_explained(carried), abs=TOL)
    assert carried.score == pytest.approx(
        carried.level_weighted - carried.penalty - carried.cap_adjustment, abs=TOL
    )
    assert {"branch", "pillar_scores", "weights_effective", "base", "contributions", "penalty",
            "cap_adjustment", "caps_fired", "level_weighted", "score", "band",
            "size_band"} == set(CARRIED_FIELDS)
    assert carried.size_band == "small"  # the band behind the liquidity score that is shown


def test_only_a_live_month_can_be_carried_into_a_stale_one(score_parts, params) -> None:
    live = score_parts.live(START, 60.0, params)
    stale = score_parts.stale(date(2025, 2, 1), 30.0, params)
    with pytest.raises(ValueError):
        carry_forward(live, live)
    with pytest.raises(ValueError):
        carry_forward(stale, carry_forward(stale, live))  # never from another carried month
    again = carry_forward(score_parts.stale(date(2025, 6, 1), 10.0, params), live)
    assert again.score == 60.0 and again.carried_from == START  # a long spell repeats the same month


def test_carried_pillars_describe_the_same_month_as_the_number() -> None:
    pillars = {
        key: PillarResult(key=key, score=70.0, inputs={"x": 1.0}, gates=("absolute_anchors",))
        for key in PILLAR_KEYS
    }
    pillars["debt"] = PillarResult(key="debt", score=None, gates=("no_debt",))
    marked = carried_pillars(pillars)
    assert list(marked) == list(PILLAR_KEYS)
    assert marked["liquidity"].gates == ("absolute_anchors", CARRIED_GATE)
    assert marked["debt"].gates == ("no_debt", CARRIED_GATE) and marked["debt"].score is None
    assert marked["liquidity"].score == 70.0 and marked["liquidity"].inputs == {"x": 1.0}
    assert pillars["liquidity"].gates == ("absolute_anchors",)  # the live month is untouched


def test_snapshot_of_a_carried_month(score_parts, params, monkeypatch) -> None:
    monkeypatch.setattr(scoring, "explain", lambda parts, pillars, p: [])
    monkeypatch.setattr(
        scoring, "delta_parts",
        lambda current, previous: DeltaParts(
            score=current.score - previous.score, base=current.base - previous.base,
            contributions={key: current.contributions[key] - previous.contributions[key]
                           for key in current.contributions},
            penalty=current.penalty - previous.penalty,
            cap_adjustment=current.cap_adjustment - previous.cap_adjustment,
        ),
    )
    pillars = {key: PillarResult(key=key, score=None, gates=("no_base",)) for key in PILLAR_KEYS}

    def month(parts: ScoreParts, verdict: Trajectory, shown: dict[str, PillarResult]) -> EntityMonth:
        row = PanelRow(entity_kind="group", entity_id="G", group_id="G", month=parts.month,
                       months_observed=parts.months_observed, cash_month_end=5.0)
        return EntityMonth(row, shown, parts, verdict)

    live = score_parts.live(START, 58.0, params)
    own = score_parts.stale(date(2025, 2, 1), 12.0, params)
    first = month(live, Trajectory(available=False, reason="short_history"), pillars)
    second = month(carry_forward(own, live), Trajectory(available=False, reason="stale_feed"),
                   carried_pillars(pillars))
    snapshot = scoring.build_snapshot(second, first, params, "hash")
    assert (snapshot.score, snapshot.level, snapshot.observed_score) == (58.0, 12.0, 12.0)
    assert snapshot.predicted_future_score == 58.0 and snapshot.carried_from == START
    assert not snapshot.feed_live and snapshot.abstained and snapshot.abstain_reason == "stale_feed"
    assert snapshot.delta == 0.0 and snapshot.delta_parts.base == 0.0
    assert all(value == 0.0 for value in snapshot.delta_parts.contributions.values())
    assert all(CARRIED_GATE in gates for gates in snapshot.gates.values())
    assert snapshot.series["cash_month_end"] == 5.0  # facts stay those of the month
    frame = scoring.snapshots_frame([scoring.build_snapshot(first, None, params, "hash"), snapshot])
    assert frame["carried_from"].to_list() == [None, START] and frame["feed_live"].to_list() == [True, False]
    assert frame["band"].to_list() == [live.band, live.band]

    shifted = month(live, Trajectory(available=True, reason=None, direction="perimeter_shift",
                                     delta3=-9.0, sigma=2.0, delta3_sigma=-4.5), pillars)
    legacy = scoring.build_snapshot(shifted, None, params, "hash")
    assert legacy.trend == "stable" and legacy.trajectory.direction == "perimeter_shift"


def test_score_entity_carries_the_last_live_month(panel_rows, params) -> None:
    rng = random.Random(71)
    live = dict(rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9,
                zero_row_month=False, entity_kind="group", entity_id="G", group_id="G",
                swept_subsidiary=False)
    dead = dict(live, rows_month=0, rows_3m=0, zero_row_month=True)
    pattern = [dead, live, live, dead, dead, live, dead]
    rows = [
        panel_rows.random(rng, month=date(2025, index + 1, 1), months_observed=index + 10, **feed)
        for index, feed in enumerate(pattern)
    ]
    months = score_entity(rows, params)
    assert [item.parts.feed_live for item in months] == [False, True, True, False, False, True, False]
    # nothing to carry before the first live month: the own arithmetic stands
    first = months[0].parts
    assert first.carried_from is None and first.score == first.level and first.abstained
    assert first.penalty == 0.0 and first.caps_fired == ()
    for index, source in ((3, 2), (4, 2), (6, 5)):
        carried, origin = months[index], months[source]
        assert carried.parts.carried_from == origin.row.month
        assert carried.parts.score == origin.parts.score and carried.parts.band == origin.parts.band
        assert carried.parts.pillar_scores == origin.parts.pillar_scores
        assert carried.parts.abstain_reason == "stale_feed" and "stale_feed" in carried.parts.flags
        assert carried.parts.score == pytest.approx(_explained(carried.parts), abs=TOL)
        assert carried.row is rows[index]
        for key in PILLAR_KEYS:
            assert carried.pillars[key].gates == (*origin.pillars[key].gates, CARRIED_GATE)
            assert carried.pillars[key].score == origin.pillars[key].score
        assert (carried.trajectory.available, carried.trajectory.reason) == (False, "stale_feed")
    for index in (1, 2, 5):
        assert months[index].parts.carried_from is None
        assert not any(CARRIED_GATE in result.gates for result in months[index].pillars.values())
    # past-only: a prefix gives the same months
    assert score_entity(rows[:5], params) == months[:5]
