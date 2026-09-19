# -*- coding: utf-8 -*-
"""
Horizontes de Rumbo: el futuro de la nota, calculado con el propio motor.

Qué hace
--------
Para cada entidad (empresa o grupo) con nota viva y sin abstención en el mes
de corte, proyecta la nota a 12 meses en varios escenarios. El futuro NUNCA se
calcula con una fórmula inventada: cada mes simulado se puntúa con las
funciones del motor (`xray_engine.pillars.compute_pillars` y
`xray_engine.aggregate.aggregate`), con sus tablas de anclas, su penalización
no compensatoria y sus topes.

Método
------
1. Métricas de entrada de los pilares. De cada mes de historia se extraen, con
   `compute_pillars(row, params, group_row).inputs`, las siete magnitudes que
   el motor convierte en puntos: días de colchón a fin de mes y en el mínimo
   del mes (liquidez; la del grupo si la empresa hereda liquidez), días sobre
   el vencimiento de proveedores y de clientes, cobertura operativa y momento
   (actividad) y peso de la deuda. Solo cuentan los meses en los que el pilar
   tiene nota. Se trabaja en un espacio transformado para que los cambios
   sean comparables entre entidades: asinh(días/10) para el colchón,
   log(ratio) para cobertura y momento, asinh(peso/0,01) para la deuda y días
   sin transformar (acotados a [-30, 90]) para la puntualidad.
2. Reconstrucción del corte. Las métricas del mes de corte se vuelven a
   escribir en la fila del panel con `dataclasses.replace` (caja = días ×
   salida diaria − disponible, cobros = cobertura × pagos, cuota = peso ×
   cobros, etc.) y se puntúan con el motor; la nota en décimas debe coincidir
   con `shown` del bundle.
3. Escenario base («si todo sigue igual»). Bootstrap por bloques de 3 meses
   de los cambios mensuales PROPIOS de la entidad (los siete a la vez, mismos
   meses, para conservar la correlación), centrados en media cero, con una
   reversión suave φ hacia la mediana propia de 12 meses. Con menos de 8
   meses de cambios se usan bloques de las entidades del mismo tipo y del
   mismo tramo de tamaño del motor (cada donante centrado en su propia
   media). Cada mes simulado se puntúa con el motor, con las puertas del
   corte congeladas (un pilar sin nota sigue sin nota) y el tope de liquidez
   negativa recalculado sobre la trayectoria simulada.
4. «Si sigue la deriva»: se añade la pendiente de Theil-Sen de 12 meses de
   cada métrica (`xray_engine.trajectory._theil_sen`). «Si se repite su peor
   trimestre»: los tres primeros meses repiten el bloque de 3 meses de
   cambios observados que, según el propio motor, deja la nota más baja.
5. Acciones del motor (`actions.plan_actions`): la métrica del pilar va de
   `current` a `target` en una rampa lineal de L meses (L = ventana de medida
   del pilar leída de params) sobre las mismas trayectorias del escenario
   base. Con ruido cero y la rampa completa la nota debe ser
   `new_score_tenths`. Las combinaciones se puntúan como hace
   `plan_actions`: pilares en su objetivo y `aggregate`.
6. Calibración. Se repite el escenario base desde cortes pasados usando solo
   datos hasta ese corte (el panel del motor es punto en el tiempo): φ se
   elige en un corte de ajuste y la cobertura se mide en un corte de
   evaluación. Si la banda del 80 % cubre menos del 80 %, se ensanchan las
   desviaciones respecto a la mediana con un factor k.

Ejecución
---------
cd ~/Developer/hackspain-motor && uv run --package xray-engine python horizontes.py \
    --panel .../panel.parquet --bundle .../bundle-main --params .../reference_v1.json \
    --out .../rumbo/horizons --cut 2026-08 --sims 400 --seed 7
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import polars as pl

from xray_engine import panel as panel_module
from xray_engine.actions import plan_actions
from xray_engine.aggregate import aggregate
from xray_engine.params import load_params
from xray_engine.pillars import compute_pillars
from xray_engine.trajectory import _theil_sen

SCHEMA = "rumbo-horizons-v1"
INDEX_SCHEMA = "rumbo-horizons-index-v1"
H = 12
BLOCK = 3
MIN_OWN_CHANGES = 8
N_GRAINS = 40
QUANTS = (10, 25, 50, 75, 90)
PHI_GRID = (0.0, 0.1, 0.2, 0.35, 0.5)
WINDOW_GRID = (12, 6, 3)  # months of the own median the reversion aims at
TUNE_SIMS = 150

METRICS = ("liq_end", "liq_min", "ap_dbt", "ar_dbt", "cov", "mom", "burden")
K = len(METRICS)
MI = {name: i for i, name in enumerate(METRICS)}
PILLAR_METRICS = {
    "liquidity": ("liq_end", "liq_min"),
    "payments": ("ap_dbt",),
    "collections": ("ar_dbt",),
    "activity": ("cov",),  # the action lever is coverage; momentum is not moved
    "debt": ("burden",),
}
REASONS = {
    "stale_feed": "La conexión bancaria no está al día en el mes de corte: el motor se abstiene y no proyectamos la nota.",
    "short_history": "Hay menos de 4 meses de historia bancaria: el motor se abstiene y no hay base para proyectar.",
    "no_bank_pillar": "Ni la liquidez ni la actividad son observables: el motor se abstiene y no proyectamos la nota.",
    "missing": "No hay datos de esta entidad en el mes de corte.",
}


# --------------------------------------------------------------------------
# months and transforms
# --------------------------------------------------------------------------


def mindex(value) -> int:
    if isinstance(value, str):
        y, m = value.split("-")[:2]
        return int(y) * 12 + int(m) - 1
    return value.year * 12 + value.month - 1


def mlabel(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def fwd(k: int, x: float) -> float:
    name = METRICS[k]
    if name in ("liq_end", "liq_min"):
        return math.asinh(x / 10.0)
    if name in ("ap_dbt", "ar_dbt"):
        return min(90.0, max(-30.0, x))
    if name in ("cov", "mom"):
        return math.log(max(x, 1e-3))
    return math.asinh(max(x, 0.0) / 0.01)


def back(y: np.ndarray) -> np.ndarray:
    """(..., K) transformed -> raw metrics."""
    x = np.empty_like(y)
    x[..., 0:2] = 10.0 * np.sinh(y[..., 0:2])
    x[..., 2:4] = np.clip(y[..., 2:4], -30.0, 90.0)
    x[..., 4:6] = np.exp(y[..., 4:6])
    x[..., 6] = 0.01 * np.sinh(np.maximum(y[..., 6], 0.0))
    return x


def clip_state(y: np.ndarray) -> None:
    y[..., 2:4] = np.clip(y[..., 2:4], -30.0, 90.0)
    y[..., 6] = np.maximum(y[..., 6], 0.0)


def clip_raw(x: np.ndarray) -> None:
    x[..., 2:4] = np.clip(x[..., 2:4], -30.0, 90.0)
    x[..., 4:6] = np.maximum(x[..., 4:6], 1e-3)
    x[..., 6] = np.maximum(x[..., 6], 0.0)


# --------------------------------------------------------------------------
# worker state
# --------------------------------------------------------------------------

G: dict = {}


def extract(pillars) -> list[float | None]:
    out: list[float | None] = [None] * K
    liq = pillars["liquidity"]
    if liq.score is not None:
        out[0] = liq.inputs.get("buffer_days_month_end")
        out[1] = liq.inputs.get("buffer_days_intra_min")
    if pillars["payments"].score is not None:
        out[2] = pillars["payments"].inputs.get("days_beyond_terms")
    if pillars["collections"].score is not None:
        out[3] = pillars["collections"].inputs.get("days_beyond_terms")
    act = pillars["activity"]
    if act.score is not None:
        out[4] = act.inputs.get("coverage")
        out[5] = act.inputs.get("momentum")
    if pillars["debt"].score is not None:
        out[6] = pillars["debt"].inputs.get("burden")
    return out


def init_worker(panel_path: str, params_path: str, bundle_dir: str, cuts: list[int]) -> None:
    P = load_params(params_path)
    df = pl.read_parquet(panel_path)
    rows: dict[tuple[str, str], list] = defaultdict(list)
    for row in panel_module.iter_rows(df):
        rows[(row.entity_kind, row.entity_id)].append(row)
    groups = {}
    for (kind, eid), rs in rows.items():
        rs.sort(key=lambda r: r.month)
        if kind == "group":
            groups[eid] = {mindex(r.month): r for r in rs}
    hist = {}
    for (kind, eid), rs in rows.items():
        first = mindex(rs[0].month)
        y = np.full((len(rs), K), np.nan)
        negflag = np.zeros(len(rs), dtype=bool)
        for i, r in enumerate(rs):
            gr = groups.get(r.group_id, {}).get(mindex(r.month)) if kind == "company" else None
            vals = extract(compute_pillars(r, P, gr))
            for k, v in enumerate(vals):
                if v is not None and v == v:
                    y[i, k] = fwd(k, v)
            cash = r.cash_month_end
            negflag[i] = cash is not None and cash == cash and cash + (r.headroom or 0.0) < 0
        hist[(kind, eid)] = (first, y, negflag)
    G.update(P=P, rows=rows, groups=groups, hist=hist, bundle=Path(bundle_dir), pools={})
    for cut in cuts:
        G["pools"][cut] = build_pools(cut)


def changes(y: np.ndarray) -> np.ndarray:
    if len(y) < 2:
        return np.zeros((0, K))
    return y[1:] - y[:-1]


def active_at(kind: str, eid: str, cut: int) -> tuple[np.ndarray, np.ndarray] | None:
    first, y, _ = G["hist"][(kind, eid)]
    n = cut - first + 1
    if n < 1 or n > len(y):
        return None
    ys = y[:n]
    return ys, ~np.isnan(ys[-1])


def blocks_of(d: np.ndarray) -> np.ndarray:
    """(nb, BLOCK, K) moving blocks; short series wrap around."""
    T = len(d)
    if T == 0:
        return np.zeros((0, BLOCK, K))
    if T < BLOCK:
        idx = np.arange(BLOCK) % T
        return d[idx][None]
    return np.stack([d[s:s + BLOCK] for s in range(T - BLOCK + 1)])


def build_pools(cut: int) -> dict:
    """Donor blocks per (kind, size band) at ``cut``: entities with at least
    MIN_OWN_CHANGES changes on every metric observed at the cut, each donor
    centred on its own means. Uses only months <= cut."""
    lib: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    cols: dict[tuple[str, str], list[list[float]]] = defaultdict(lambda: [[] for _ in range(K)])
    for (kind, eid), rs in G["rows"].items():
        got = active_at(kind, eid, cut)
        if got is None:
            continue
        ys, act = got
        if not act.any():
            continue
        d = changes(ys)
        counts = (~np.isnan(d)).sum(axis=0)
        if len(d) == 0 or counts[act].min() < MIN_OWN_CHANGES:
            continue
        row = rs[cut - mindex(rs[0].month)]
        band = row.size_band or "unknown"
        with np.errstate(all="ignore"):
            means = np.array([np.nanmean(d[:, k]) if counts[k] else 0.0 for k in range(K)])
        dc = d - means
        for key in ((kind, band), (kind, "*")):
            lib[key].append(blocks_of(dc))
            for k in range(K):
                cols[key][k].extend(dc[~np.isnan(dc[:, k]), k].tolist())
    return {
        key: (np.concatenate(v) if v else np.zeros((0, BLOCK, K)), [np.array(c) for c in cols[key]])
        for key, v in lib.items()
    }


# --------------------------------------------------------------------------
# engine scoring of simulated metrics
# --------------------------------------------------------------------------


@dataclass
class Ctx:
    kind: str
    eid: str
    row: object
    grow: object
    inherited: bool
    daily: float | None
    src_head: float
    src_head_min: float
    active: np.ndarray
    negflags_hist: np.ndarray  # months cut-5..cut, own row
    own_cash_cap: bool
    memo: dict


def make_ctx(kind: str, eid: str, cut: int) -> Ctx | None:
    rs = G["rows"][(kind, eid)]
    i = cut - mindex(rs[0].month)
    if i < 0 or i >= len(rs):
        return None
    row = rs[i]
    grow = G["groups"].get(row.group_id, {}).get(cut) if kind == "company" else None
    inherited = bool(row.swept_subsidiary) and grow is not None
    src = grow if inherited else row
    monthly = None
    if src.outflow_median_3m is not None and src.outflow_median_3m > 0:
        monthly = src.outflow_median_3m
    elif src.outflow_median_12m is not None and src.outflow_median_12m > 0:
        monthly = src.outflow_median_12m
    daily = monthly / G["P"].liquidity.days_per_month if monthly else None
    first, y, negflag = G["hist"][(kind, eid)]
    flags = np.zeros(6, dtype=bool)  # months cut-5 .. cut
    for j in range(6):
        pos = i - 5 + j
        if pos >= 0:
            flags[j] = negflag[pos]
    return Ctx(kind, eid, row, grow, inherited, daily, src.headroom or 0.0, src.headroom_at_min or 0.0,
               ~np.isnan(y[i]), flags, not inherited, {})


def materialize(ctx: Ctx, x: np.ndarray, neg: int | None):
    """Raw metrics (K,) -> (row, group_row) carrying them; only active metrics are written."""
    r, gr, a = ctx.row, ctx.grow, ctx.active
    upd = {}
    if a[0]:
        liq = dict(cash_month_end=float(x[0]) * ctx.daily - ctx.src_head,
                   cash_intra_month_min=float(x[1]) * ctx.daily - ctx.src_head_min)
        if ctx.inherited:
            gr = replace(gr, **liq)
        else:
            upd.update(liq)
    if a[2]:
        upd["ap_days_beyond_terms"] = float(x[2])
    if a[3]:
        upd["ar_days_beyond_terms"] = float(x[3])
    if a[4]:
        upd["op_in_sum_6m_w"] = float(x[4]) * r.outflow_sum_6m_w
    if a[5]:
        upd["op_in_lfl_recent_mean"] = float(x[5]) * r.op_in_lfl_prior_mean
    if a[6]:
        upd["debt_service_sum_12m_w"] = max(float(x[6]), 1e-12) * r.op_in_sum_12m_w
    if neg is not None:
        upd["neg_liquidity_months_6m"] = int(neg)
    return replace(r, **upd), gr


def engine_parts(ctx: Ctx, x: np.ndarray, neg: int | None):
    row, gr = materialize(ctx, x, neg)
    return aggregate(compute_pillars(row, G["P"], gr), row, G["P"], gr)


def tenths(score: float) -> int:
    return round(min(100.0, max(0.0, score)) * 10)


def engine_tenths(ctx: Ctx, x: np.ndarray, neg: int | None) -> int:
    key = (tuple(np.round(x, 12).tolist()), neg)
    got = ctx.memo.get(key)
    if got is None:
        got = tenths(engine_parts(ctx, x, neg).score)
        if len(ctx.memo) < 200000:
            ctx.memo[key] = got
    return got


def score_paths(ctx: Ctx, raw: np.ndarray) -> np.ndarray:
    """raw (N, h, K) -> engine tenths (N, h). The negative-liquidity cap reads
    months t-5..t of cash + headroom < 0: history for months <= cut, the
    simulated month-end buffer after it."""
    N, Hh, _ = raw.shape
    out = np.empty((N, Hh), dtype=np.int32)
    track_neg = ctx.active[0] and ctx.own_cash_cap
    simneg = raw[:, :, 0] < 0 if track_neg else None
    for h in range(1, Hh + 1):
        if track_neg:
            hist = int(ctx.negflags_hist[h:].sum()) if h < 6 else 0
            negs = hist + simneg[:, max(0, h - 6):h].sum(axis=1)
        for n in range(N):
            out[n, h - 1] = engine_tenths(ctx, raw[n, h - 1], int(negs[n]) if track_neg else None)
    return out


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------


@dataclass
class Model:
    y0: np.ndarray  # (K,) transformed state at the cut (0 where inactive)
    med: np.ndarray  # own 12-month median
    slope: np.ndarray  # Theil-Sen slope per month
    c_off: np.ndarray  # months from the centre of the slope window to the cut
    blocks: np.ndarray  # (nb, BLOCK, K) centred changes
    fill: list  # per metric, values used for missing entries
    raw_d: np.ndarray  # own raw changes (T, K)
    pooled: bool


def build_model(kind: str, eid: str, cut: int, ctx: Ctx, center: bool = True, window: int = 12) -> Model:
    ys, act = active_at(kind, eid, cut)
    d = changes(ys)
    counts = (~np.isnan(d)).sum(axis=0) if len(d) else np.zeros(K, dtype=int)
    n_changes = int(counts[act].min()) if act.any() else 0
    pooled = n_changes < MIN_OWN_CHANGES
    band = ctx.row.size_band or "unknown"
    pools = G["pools"][cut]
    pool = pools.get((kind, band))
    if pool is None or len(pool[0]) < 30:
        pool = pools.get((kind, "*"), (np.zeros((0, BLOCK, K)), [np.array([]) for _ in range(K)]))
    with np.errstate(all="ignore"):
        means = np.array([np.nanmean(d[:, k]) if counts[k] else 0.0 for k in range(K)])
    dc = d - means if center else d.copy()
    if pooled:
        blocks, fill = pool[0], list(pool[1])
    else:
        blocks = blocks_of(dc)
        fill = [dc[~np.isnan(dc[:, k]), k] if counts[k] >= 3 else pool[1][k] for k in range(K)]
    last = ys[-12:]
    recent = ys[-window:]
    y0 = np.where(act, np.nan_to_num(ys[-1]), 0.0)
    med = np.zeros(K)
    slope = np.zeros(K)
    c_off = np.zeros(K)
    for k in range(K):
        valid_r = ~np.isnan(recent[:, k])
        if valid_r.any():
            med[k] = float(np.median(recent[valid_r, k]))
            # months between the centre of the median window and the cut
            c_off[k] = float(np.mean([len(recent) - 1 - j for j in range(len(recent)) if valid_r[j]]))
        valid = ~np.isnan(last[:, k])
        pts = [(j, float(last[j, k])) for j in range(len(last)) if valid[j]]
        if len(pts) >= 4:
            slope[k] = _theil_sen(pts)
    return Model(y0, med, slope, c_off, blocks, fill, d, pooled)


def draw(model: Model, rng: np.random.Generator, N: int, Hh: int) -> np.ndarray:
    nblk = math.ceil(Hh / BLOCK)
    if len(model.blocks) == 0:
        D = np.full((N, Hh, K), np.nan)
    else:
        idx = rng.integers(0, len(model.blocks), size=(N, nblk))
        D = model.blocks[idx].reshape(N, nblk * BLOCK, K)[:, :Hh].copy()
    for k in range(K):
        mask = np.isnan(D[:, :, k])
        cnt = int(mask.sum())
        if cnt:
            vals = model.fill[k]
            D[:, :, k][mask] = rng.choice(vals, cnt) if len(vals) else 0.0
    return D


def simulate(model: Model, D: np.ndarray, phi: float, drift: bool = False,
             stress: np.ndarray | None = None) -> np.ndarray:
    N, Hh, _ = D.shape
    y = np.repeat(model.y0[None], N, axis=0)
    out = np.empty((N, Hh, K))
    for h in range(1, Hh + 1):
        d = D[:, h - 1]
        if stress is not None and h <= len(stress):
            d = np.repeat(stress[h - 1][None], N, axis=0)
        target = model.med + (model.slope * (h + model.c_off) if drift else 0.0)
        y = y + d + (model.slope if drift else 0.0) - phi * (y - target)
        clip_state(y)
        out[:, h - 1] = y
    return back(out)


def worst_block(ctx: Ctx, model: Model, phi: float) -> np.ndarray:
    d = np.nan_to_num(model.raw_d)
    if len(d) == 0:
        return np.zeros((BLOCK, K))
    cands = blocks_of(d) if len(d) >= BLOCK else d[None]
    best, best_score = cands[0], None
    for c in cands:
        raw = simulate(model, np.zeros((1, len(c), K)), phi, stress=c)
        s = score_paths(ctx, raw)[0, -1]
        if best_score is None or s < best_score:
            best, best_score = c, s
    return best


# --------------------------------------------------------------------------
# summaries
# --------------------------------------------------------------------------

BAND_KEYS = ("critical", "watch", "stable", "solid")


def band_idx(t: np.ndarray, mins: list[int]) -> np.ndarray:
    return np.searchsorted(np.array(mins), t, side="right") - 1


def widen(S: np.ndarray, k: float) -> np.ndarray:
    if k == 1.0:
        return S
    med = np.median(S, axis=0, keepdims=True)
    return np.clip(np.rint(med + k * (S - med)), 0, 1000).astype(np.int32)


def fan(S: np.ndarray, months: list[str], shown: int, mins: list[int]) -> dict:
    q = {f"p{p}": np.rint(np.percentile(S, p, axis=0)).astype(int).tolist() for p in QUANTS}
    bi = band_idx(S, mins)
    bands = {}
    for name, h in (("h3", 3), ("h6", 6), ("h12", 12)):
        col = bi[:, h - 1]
        bands[name] = {BAND_KEYS[b]: round(float((col == b).mean()), 2) for b in range(4)}
    now = int(band_idx(np.array([shown]), mins)[0])
    cross = None
    for h in range(S.shape[1]):
        col = bi[:, h]
        down, up = float((col < now).mean()), float((col > now).mean())
        if down >= 0.5 or up >= 0.5:
            worse = down >= 0.5
            sel = col[col < now] if worse else col[col > now]
            to = int(np.bincount(sel).argmax())
            cross = {"dir": "down" if worse else "up", "to": BAND_KEYS[to], "month": months[h],
                     "prob": round(down if worse else up, 2)}
            break
    grains = [[h + 1, int(S[n, h])] for n in range(min(N_GRAINS, len(S))) for h in range(S.shape[1])]
    return {"q": q, "bands": bands, "cross": cross, "grains": grains}


def crps(sims: np.ndarray, obs: float) -> float:
    x = np.sort(sims.astype(float))
    n = len(x)
    term1 = np.abs(x - obs).mean()
    term2 = (2 * np.arange(1, n + 1) - n - 1) @ x / (n * n)
    return float(term1 - term2)


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------


def load_entity(kind: str, eid: str) -> dict:
    sub = "companies" if kind == "company" else "groups"
    with open(G["bundle"] / sub / f"{eid}.json", encoding="utf-8") as fh:
        return json.load(fh)


def rng_for(seed: int, eid: str, stage: int) -> np.random.Generator:
    return np.random.default_rng([seed, zlib.crc32(eid.encode()), stage])


def month_entry(doc: dict, label: str) -> dict | None:
    for m in doc["months"]:
        if m["month"] == label:
            return m
    return None


def eligible(doc: dict, label: str) -> tuple[dict | None, str | None]:
    entry = month_entry(doc, label)
    if entry is None:
        return None, "missing"
    if entry["abstain"] is not None:
        return entry, entry["abstain"]["reason"]
    if not entry["feed_live"]:
        return entry, "stale_feed"
    return entry, None


def run_backtest(task) -> dict | None:
    """Baseline from a past cut, only data up to it. mode 'tune': grid of phi
    (and centring) with TUNE_SIMS; mode 'eval': chosen phi, base and drift."""
    kind, eid, cut, mode, cfg, sims, seed = task
    doc = load_entity(kind, eid)
    entry, reason = eligible(doc, mlabel(cut))
    if entry is None or reason is not None:
        return None
    ctx = make_ctx(kind, eid, cut)
    if ctx is None:
        return None
    rec = {"id": eid, "kind": kind, "shown": entry["shown"]}
    x0 = back(np.where(ctx.active, build_model(kind, eid, cut, ctx).y0, 0.0))
    rec["h0_ok"] = abs(engine_tenths(ctx, x0, None) - entry["shown"]) == 0
    real = {}
    for h in (3, 6):
        e = month_entry(doc, mlabel(cut + h))
        if e is not None and e["feed_live"] and e["abstain"] is None:
            real[h] = e["shown"]
    rec["real"] = real
    if not real:
        return rec
    if mode == "tune":
        out = {}
        grid = [(True, w) for w in WINDOW_GRID] + [(False, 12)]
        for center, window in grid:
            model = build_model(kind, eid, cut, ctx, center=center, window=window)
            D = draw(model, rng_for(seed, eid, 11), sims, 6)
            for ph in PHI_GRID:
                if ph == 0.0 and window != 12:
                    continue  # no reversion: the window plays no part
                S = score_paths(ctx, simulate(model, D, ph))
                out[f"{'c' if center else 'n'}{window}/{ph}"] = {h: S[:, h - 1].tolist() for h in real}
        rec["sims"] = out
    else:
        phi, window = cfg
        model = build_model(kind, eid, cut, ctx, window=window)
        D = draw(model, rng_for(seed, eid, 12), sims, 6)
        rec["pooled"] = model.pooled
        rec["base"] = {h: v.tolist() for h, v in zip((3, 6), score_paths(ctx, simulate(model, D, phi))[:, [2, 5]].T)}
        rec["drift"] = {h: v.tolist() for h, v in zip((3, 6), score_paths(ctx, simulate(model, D, phi, drift=True))[:, [2, 5]].T)}
    return rec


def run_production(task) -> dict:
    kind, eid, cut, (phi, window), k, sims, seed, out_dir, meta = task
    doc = load_entity(kind, eid)
    months = [mlabel(cut + h) for h in range(1, H + 1)]
    head = {"schema": SCHEMA, "entity_id": eid, "entity_kind": kind,
            "group_id": doc.get("group_id", eid), "cut": mlabel(cut),
            "bundle_id": meta["bundle_id"], "params_hash": meta["params_hash"], "months": months}
    entry, reason = eligible(doc, mlabel(cut))
    ctx = make_ctx(kind, eid, cut) if reason is None else None
    summary = {"kind": kind, "p50_h6": None, "p_critical_h6": None, "cross": None,
               "shown_at_cut": entry["shown"] if entry else None}
    if reason is not None or ctx is None:
        reason = reason or "missing"
        data = {**head, "shown_at_cut": summary["shown_at_cut"], "scenarios": None,
                "reason": REASONS.get(reason, REASONS["missing"]), "reason_code": reason,
                "actions": [], "combos": []}
        write_json(Path(out_dir) / f"{eid}.json", data)
        return {"id": eid, "summary": summary, "skipped": reason}

    P, mins = G["P"], meta["band_mins"]
    shown = entry["shown"]
    model = build_model(kind, eid, cut, ctx, window=window)
    x0 = back(model.y0)
    h0 = engine_tenths(ctx, x0, None)
    D = draw(model, rng_for(seed, eid, 1), sims, H)
    base_raw = simulate(model, D, phi)
    S_base = score_paths(ctx, base_raw)
    S_drift = score_paths(ctx, simulate(model, D, phi, drift=True))
    stress = worst_block(ctx, model, phi)
    S_stress = score_paths(ctx, simulate(model, D, phi, stress=stress))
    scen = {name: fan(widen(S, k), months, shown, mins)
            for name, S in (("base", S_base), ("drift", S_drift), ("stress", S_stress))}

    # engine actions at the cut, recomputed exactly and matched with the bundle
    row, gr = ctx.row, ctx.grow
    pillars = compute_pillars(row, P, gr)
    parts = aggregate(pillars, row, P, gr)
    plan = plan_actions(row, pillars, parts, P, gr)
    bundle_actions = {a["id"]: a for a in entry.get("actions", [])}
    lags = meta["lags"]
    actions_out, checks = [], []
    for action in plan.actions:
        b = bundle_actions.get(action.id)
        idx = [MI[m] for m in PILLAR_METRICS[action.pillar]]
        offset = np.zeros(K)
        if action.pillar == "liquidity":
            # same extra days on both buffers, as plan_actions does
            offset[idx] = action.target - action.current
        else:
            # full ramp lands exactly on the target (the log floor of a zero
            # coverage must not shift it)
            goal = action.target / 100.0 if action.pillar == "debt" else action.target
            offset[idx] = goal - x0[idx]
        # zero noise, full ramp, other inputs and row facts at the cut
        x_full = x0.copy() + offset
        clip_raw(x_full)
        det = tenths(engine_parts(ctx, x_full, None).score)
        expected = b["new_score_tenths"] if b else action.new_score_tenths
        ok = abs(det - expected) <= 1
        checks.append(ok)
        L = lags[action.pillar]
        ramp = np.minimum(1.0, np.arange(1, H + 1) / L)
        raw = base_raw + ramp[None, :, None] * offset[None, None, :]
        clip_raw(raw)
        S_act = score_paths(ctx, raw)
        actions_out.append({"id": action.id, "pillar": action.pillar, "lag_months": L,
                            "current": round(action.current, 4), "target": round(action.target, 4),
                            "engine_new_score": expected, "deterministic_new_score": det,
                            **fan(widen(S_act, k), months, shown, mins), "consistency_ok": ok,
                            "in_bundle": b is not None})
    combos, combo_checks = [], []
    kept = list(plan.actions)
    for size in range(2, len(kept) + 1):
        for subset in itertools.combinations(kept, size):
            changed = dict(pillars)
            for a in subset:
                changed[a.pillar] = replace(pillars[a.pillar], score=a.pillar_target)
            score = tenths(aggregate(changed, row, P, gr).score)
            combos.append({"ids": sorted(a.id for a in subset), "new_score": score})
            if size == len(kept):
                combined = entry.get("actions_combined", {}).get("new_score")
                combo_checks.append(combined is not None and abs(max(shown, score) - combined) <= 1)
    ids_match = sorted(a.id for a in plan.actions) == sorted(bundle_actions)

    base = scen["base"]
    data = {**head, "shown_at_cut": shown, "scenarios": scen, "actions": actions_out, "combos": combos,
            "method": {"sims": sims, "block": BLOCK, "phi": phi, "median_window": window, "widen_k": k, "pooled": model.pooled,
                       "lags": lags, "h0_reproduced": h0 == shown}}
    write_json(Path(out_dir) / f"{eid}.json", data)
    bi = band_idx(widen(S_base, k)[:, 5], mins)
    summary.update(p50_h6=base["q"]["p50"][5], p_critical_h6=round(float((bi == 0).mean()), 2),
                   cross=base["cross"])
    return {"id": eid, "summary": summary, "h0_ok": h0 == shown, "h0": h0, "shown": shown,
            "actions_ok": checks, "combos_ok": combo_checks, "ids_match": ids_match,
            "pooled": model.pooled,
            "p50": {name: [scen[name]["q"]["p50"][h - 1] for h in (3, 6, 12)] for name in scen},
            "acts": [(a["id"], a["engine_new_score"], [a["q"]["p50"][h - 1] for h in (3, 6, 12)]) for a in actions_out]}


def write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def coverage_stats(pairs: list[tuple[np.ndarray, int]], k: float) -> dict:
    c50 = c80 = 0
    pit = np.zeros(10)
    for sims, obs in pairs:
        s = widen(sims[:, None], k)[:, 0] if k != 1.0 else sims
        q10, q25, q75, q90 = np.percentile(s, [10, 25, 75, 90])
        c50 += q25 <= obs <= q75
        c80 += q10 <= obs <= q90
        u = ((s < obs).sum() + 0.5 * (s == obs).sum()) / len(s)
        pit[min(9, int(u * 10))] += 1
    n = max(1, len(pairs))
    return {"cov50": round(c50 / n, 3), "cov80": round(c80 / n, 3), "pit": (pit / n).round(3).tolist(), "n": len(pairs)}


def fit_k(pairs: list[tuple[np.ndarray, int]]) -> float:
    best, gap = 1.0, None
    for k in np.arange(1.0, 4.01, 0.05):
        cov = coverage_stats(pairs, float(k))["cov80"]
        g = abs(cov - 0.80)
        if gap is None or g < gap - 1e-12:
            best, gap = float(round(k, 2)), g
        if cov >= 0.80:
            break
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--panel", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cut", required=True)
    ap.add_argument("--sims", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--eval-back", type=int, default=6, help="evaluation cut = cut - N months")
    ap.add_argument("--tune-back", type=int, default=9, help="tuning cut = cut - N months")
    ap.add_argument("--limit", type=int, default=0, help="only the first N entities (testing)")
    args = ap.parse_args()
    t0 = time.time()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = Path(args.bundle).expanduser()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    band_mins = [b["min"] for b in manifest["bands"]]
    assert [b["key"] for b in manifest["bands"]] == list(BAND_KEYS)
    P = load_params(args.params)
    lags = {
        "liquidity": 1,  # month-end cash + undrawn lines: a point-in-time stock
        "payments": max(1, round(P.invoices.window_days / 30)),
        "collections": max(1, round(P.invoices.window_days / 30)),
        "activity": P.activity.coverage_window_months,
        "debt": P.debt.window_months,
    }
    cut = mindex(args.cut)
    cut_eval, cut_tune = cut - args.eval_back, cut - args.tune_back
    ents = sorted(
        {(k, e) for k, e in pl.read_parquet(args.panel, columns=["entity_kind", "entity_id"]).unique().iter_rows()},
        key=lambda t: (t[0] != "company", t[1]),
    )
    if args.limit:
        ents = ents[: args.limit // 2] + [e for e in ents if e[0] == "group"][: args.limit - args.limit // 2]
    log(f"{len(ents)} entities; cut {mlabel(cut)}, tuning {mlabel(cut_tune)}, evaluation {mlabel(cut_eval)}")
    ctxp = get_context("spawn")
    with ctxp.Pool(args.workers, initializer=init_worker,
                   initargs=(str(Path(args.panel).expanduser()), str(Path(args.params).expanduser()),
                             str(bundle), [cut, cut_eval, cut_tune])) as pool:
        # 1. tuning of phi (and centring diagnostic)
        tasks = [(k, e, cut_tune, "tune", None, TUNE_SIMS, args.seed) for k, e in ents]
        tune = [r for r in pool.imap_unordered(run_backtest, tasks, chunksize=4) if r]
        log(f"tuning done: {len(tune)} entities")
        crps_by: dict[str, list[float]] = defaultdict(list)
        cov_tune: dict[str, list] = defaultdict(list)
        for r in tune:
            for cfg, by_h in r.get("sims", {}).items():
                for h, s in by_h.items():
                    crps_by[cfg].append(crps(np.array(s), r["real"][h]) / 10)
                    cov_tune[cfg].append((np.array(s), r["real"][h]))
        crps_mean = {cfg: round(float(np.mean(v)), 3) for cfg, v in crps_by.items()}
        best = min((c for c in crps_mean if c.startswith("c")), key=lambda c: crps_mean[c])
        window, phi = int(best[1:].split("/")[0]), float(best.split("/")[1])
        k_tune = fit_k(cov_tune[best])
        log(f"CRPS (points) by config: {crps_mean}; best {best}; k fitted on tuning cut={k_tune}")

        # 2. evaluation cut
        tasks = [(k, e, cut_eval, "eval", (phi, window), args.sims, args.seed) for k, e in ents]
        ev = [r for r in pool.imap_unordered(run_backtest, tasks, chunksize=4) if r]
        log(f"evaluation done: {len(ev)} entities")
        pairs = {3: [], 6: []}
        dpairs = {3: [], 6: []}
        mae_med, mae_naive, mae_drift = [], [], []
        crps_base, crps_drift, crps_naive = [], [], []
        for r in ev:
            for h, obs in r["real"].items():
                h = int(h)
                s = np.array(r["base"][h])
                sd = np.array(r["drift"][h])
                pairs[h].append((s, obs))
                dpairs[h].append((sd, obs))
                mae_med.append(abs(np.median(s) - obs) / 10)
                mae_drift.append(abs(np.median(sd) - obs) / 10)
                mae_naive.append(abs(r["shown"] - obs) / 10)
                crps_base.append(crps(s, obs) / 10)
                crps_drift.append(crps(sd, obs) / 10)
        allpairs = pairs[3] + pairs[6]
        k_eval = fit_k(allpairs)
        k = k_eval
        raw = {f"h{h}": coverage_stats(pairs[h], 1.0) for h in (3, 6)}
        wid = {f"h{h}": coverage_stats(pairs[h], k) for h in (3, 6)}
        oos = {f"h{h}": coverage_stats(pairs[h], k_tune) for h in (3, 6)}
        drift_cov = {f"h{h}": coverage_stats(dpairs[h], k) for h in (3, 6)}
        pit_w = coverage_stats(allpairs, k)["pit"]
        pit_raw = coverage_stats(allpairs, 1.0)["pit"]
        h0_eval = sum(1 for r in ev if r.get("h0_ok")), len(ev)
        h0_tune = sum(1 for r in tune if r.get("h0_ok")), len(tune)
        calibration = {
            "eval_cut": mlabel(cut_eval), "tune_cut": mlabel(cut_tune),
            "h3": {"cov50": wid["h3"]["cov50"], "cov80": wid["h3"]["cov80"], "n": wid["h3"]["n"],
                   "cov50_raw": raw["h3"]["cov50"], "cov80_raw": raw["h3"]["cov80"],
                   "cov50_k_tune": oos["h3"]["cov50"], "cov80_k_tune": oos["h3"]["cov80"]},
            "h6": {"cov50": wid["h6"]["cov50"], "cov80": wid["h6"]["cov80"], "n": wid["h6"]["n"],
                   "cov50_raw": raw["h6"]["cov50"], "cov80_raw": raw["h6"]["cov80"],
                   "cov50_k_tune": oos["h6"]["cov50"], "cov80_k_tune": oos["h6"]["cov80"]},
            "pit": pit_w, "pit_raw": pit_raw,
            "mae_median": round(float(np.mean(mae_med)), 2), "mae_naive": round(float(np.mean(mae_naive)), 2),
            "mae_median_drift": round(float(np.mean(mae_drift)), 2),
            "crps_base": round(float(np.mean(crps_base)), 2), "crps_drift": round(float(np.mean(crps_drift)), 2),
            "drift_cov": {h: {"cov50": v["cov50"], "cov80": v["cov80"]} for h, v in drift_cov.items()},
            "widen_k": k, "widen_k_tune": k_tune, "n": len(allpairs), "n_entities": len(ev),
            "pooled_share": round(float(np.mean([r.get("pooled", False) for r in ev if "base" in r])), 3),
            "tuning_crps": crps_mean, "units": "puntos (0-100)",
        }
        split = {}
        for name, keep in (("company", lambda r: r["kind"] == "company"), ("group", lambda r: r["kind"] == "group"),
                           ("own_history", lambda r: not r.get("pooled")), ("pooled", lambda r: r.get("pooled"))):
            sel = [(np.array(r["base"][h]), obs) for r in ev if "base" in r and keep(r) for h, obs in r["real"].items()]
            st = coverage_stats(sel, k)
            mm = [abs(np.median(sv) - ob) / 10 for sv, ob in sel]
            nv = [abs(r["shown"] - obs) / 10 for r in ev if "base" in r and keep(r) for obs in r["real"].values()]
            split[name] = {"cov50": st["cov50"], "cov80": st["cov80"], "n": st["n"],
                           "mae_median": round(float(np.mean(mm)), 2) if mm else None,
                           "mae_naive": round(float(np.mean(nv)), 2) if nv else None}
        calibration["split"] = split
        log(f"calibration: {json.dumps(calibration)}")

        # 3. production
        meta = {"bundle_id": manifest["bundle_id"], "params_hash": manifest["params_hash"],
                "band_mins": band_mins, "lags": lags}
        tasks = [(kk, e, cut, (phi, window), k, args.sims, args.seed, str(out_dir), meta) for kk, e in ents]
        prod = []
        for i, r in enumerate(pool.imap_unordered(run_production, tasks, chunksize=2)):
            prod.append(r)
            if (i + 1) % 200 == 0:
                log(f"production {i + 1}/{len(tasks)}")
    live = [r for r in prod if "skipped" not in r]
    h0_ok = sum(1 for r in live if r["h0_ok"])
    acts = [ok for r in live for ok in r["actions_ok"]]
    combs = [ok for r in live for ok in r["combos_ok"]]
    ids_match = sum(1 for r in live if r["ids_match"])
    method = {"sims": args.sims, "block": BLOCK, "phi": phi, "median_window": window, "widen_k": k, "lags": lags,
              "min_own_changes": MIN_OWN_CHANGES, "metrics": list(METRICS), "seed": args.seed,
              "grains": "pares [h, décimas]; h = 1..12; 12 pares consecutivos por trayectoria",
              "pooled_entities": sum(1 for r in live if r["pooled"])}
    index = {
        "schema": INDEX_SCHEMA, "cut": mlabel(cut), "bundle_id": manifest["bundle_id"],
        "params_hash": manifest["params_hash"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": method, "calibration": calibration,
        "checks": {"h0_reproduced": f"{h0_ok}/{len(live)}", "actions_consistent": f"{sum(acts)}/{len(acts)}",
                   "combos_consistent": f"{sum(combs)}/{len(combs)}", "action_ids_match_bundle": f"{ids_match}/{len(live)}",
                   "h0_reproduced_eval_cut": f"{h0_eval[0]}/{h0_eval[1]}", "h0_reproduced_tune_cut": f"{h0_tune[0]}/{h0_tune[1]}"},
        "entities": {r["id"]: r["summary"] for r in sorted(prod, key=lambda r: r["id"])},
    }
    write_json(out_dir / "index.json", index)
    # diagnostics for the report (not part of the contract)
    diag = {"h0_mismatch": [(r["id"], r["h0"], r["shown"]) for r in live if not r["h0_ok"]],
            "action_fail": [(r["id"]) for r in live if not all(r["actions_ok"])],
            "combo_fail": [(r["id"]) for r in live if not all(r["combos_ok"])],
            "skipped": defaultdict(int), "examples": {r["id"]: {"p50": r["p50"], "acts": r["acts"], "shown": r["shown"]} for r in live}}
    for r in prod:
        if "skipped" in r:
            diag["skipped"][r["skipped"]] += 1
    Path("/tmp/horizons-diag.json").write_text(json.dumps(diag, default=str), encoding="utf-8")
    # every file must parse
    bad = 0
    for path in out_dir.glob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            bad += 1
    log(f"checks: {index['checks']}; skipped: {dict(diag['skipped'])}; json parse failures: {bad}")
    log(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
