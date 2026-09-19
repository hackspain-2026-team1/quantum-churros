"""The score forecast: it learns from the past only, its quantiles are ordered and it is deterministic."""

from __future__ import annotations

import numpy as np
from xray_engine import forecast as F


def _historias(n: int = 80, meses: int = 24, semilla: int = 3) -> dict[str, F.Historia]:
    """Entities whose score reverts to its own level with noise: something a model can learn."""
    rng = np.random.default_rng(semilla)
    out = {}
    for k in range(n):
        nivel = rng.uniform(25, 85)
        s = np.empty(meses)
        s[0] = nivel + rng.normal(0, 8)
        for t in range(1, meses):
            s[t] = np.clip(s[t - 1] + 0.35 * (nivel - s[t - 1]) + rng.normal(0, 6), 0, 100)
        pil = np.clip(s[:, None] + rng.normal(0, 5, (meses, 5)), 0, 100)
        eid = f"COMP_{k:04d}"
        out[eid] = F.Historia("company", eid, "GROUP_0001", F.mindex("2024-09"), s, pil,
                              np.full(meses, 0.8), np.arange(1, meses + 1, dtype=float), np.zeros(meses), ["micro"] * meses)
    return out


def test_a_model_trained_at_a_cut_never_sees_what_came_after() -> None:
    hs = _historias()
    corte = F.mindex("2025-10")
    antes = F.Pares(hs).modelos(corte)
    # Change everything after the cut: the models trained up to the cut must not move.
    for hi in hs.values():
        hi.s[hi.pos(corte) + 1:] = 100.0 - hi.s[hi.pos(corte) + 1:]
    despues = F.Pares(hs).modelos(corte)
    assert antes.keys() == despues.keys() and antes
    for h in antes:
        assert np.allclose(antes[h].beta, despues[h].beta) and np.allclose(antes[h].qz, despues[h].qz)


def test_quantiles_are_ordered_and_bounded() -> None:
    hs = _historias()
    pares = F.Pares(hs)
    mods = pares.modelos(int(pares.cortes.max()))
    Q = mods[3].predecir(pares.X[:50], pares.s0[:50])
    assert (np.diff(Q, axis=1) >= 0).all() and Q.min() >= 0 and Q.max() <= 100


def test_it_beats_no_change_on_a_process_that_reverts() -> None:
    hs = _historias(n=200)
    pares = F.Pares(hs)
    ultimo = int(pares.cortes.max())
    val = F.validar(pares, list(range(ultimo - 8, ultimo)), ultimo)
    h3 = val["por_horizonte"]["h3"]
    assert h3["error_mediana"] < h3["error_sin_cambio"]
    assert 0.65 <= h3["acierta_80"] <= 0.95


def test_the_fan_is_deterministic_and_has_its_grains() -> None:
    Q = np.array([[30, 35, 40, 45, 50]] * 12, dtype=float)
    meses = [F.mlabel(F.mindex("2026-08") + h) for h in range(1, 13)]
    a = F.abanico(Q, meses, 400, [0, 400, 600, 800], 24)
    b = F.abanico(Q, meses, 400, [0, 400, 600, 800], 24)
    assert a == b
    assert len(a["grains"]) == 24 * 12 and a["q"]["p50"][0] == 400
    assert abs(sum(a["bands"]["h6"].values()) - 1) < 0.02
