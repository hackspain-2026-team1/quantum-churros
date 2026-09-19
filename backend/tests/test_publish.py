import datetime

import polars as pl
import pytest
from app.publish import _flatten

SPEC = (
    ("entity_id", "text", "entity_id", None),
    ("month", "date", "month", None),
    ("pillars_liquidity", "float", "pillars", "liquidity"),
    ("flags", "jsonb", "flags", None),
)
RUN = {"dataset_hash": "d" * 64, "params_hash": "p" * 12}


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "entity_id": ["GROUP_T001"],
            "month": [datetime.date(2026, 8, 1)],
            "pillars": [{"liquidity": 61.5}],
            "flags": [["stale_feed"]],
        }
    )


def test_structs_become_columns_and_nested_values_json() -> None:
    flat = _flatten(_frame(), SPEC, RUN)
    assert flat.columns == ["dataset_hash", "params_hash", "entity_id", "month", "pillars_liquidity", "flags"]
    assert flat.row(0)[4:] == (61.5, '["stale_feed"]')


def test_engine_schema_drift_is_refused() -> None:
    with pytest.raises(ValueError, match="drifted"):
        _flatten(_frame().drop("flags"), SPEC, RUN)
