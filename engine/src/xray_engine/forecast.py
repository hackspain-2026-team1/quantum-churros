"""Previsión del score: un modelo predictivo entrenado con la historia de la cartera.

Qué predice
-----------
El score de cada entidad (empresa o grupo) dentro de h = 1..12 meses, con su
incertidumbre: los cuantiles 10, 25, 50, 75 y 90.

Cómo aprende
------------
Un modelo por horizonte h, entrenado con todos los pares (entidad, mes de corte
t) de la historia en los que el score era vivo en t y en t + h (conexión
bancaria al día y sin abstención). Cada par solo usa lo que se sabía en t: el
panel del motor es punto en el tiempo y las variables salen de los scores
hasta t.

1. Mediana. Regresión cuantílica lineal (τ = 0,5, mínimos desvíos absolutos
   por mínimos cuadrados reponderados, con cresta) del cambio s(t + h) − s(t)
   sobre las variables del corte: el score y sus pilares, sus cambios a 1, 3 y
   6 meses, la pendiente y la volatilidad de 12 meses, la distancia a su media
   de 12 meses, la confianza, los meses observados, el tamaño y si hay tope.
2. Escala. Regresión del error absoluto de la mediana sobre las mismas
   variables: cada entidad tiene su propia incertidumbre.
3. Cuantiles. Los errores estandarizados (error / escala) de los últimos
   meses del entrenamiento, que el modelo no ha visto al ajustarse, dan los
   multiplicadores de cada cuantil (calibración conformal en el tiempo).

Validación
----------
Origen móvil: para cada corte de validación se entrena solo con pares cuyo
mes objetivo es igual o anterior al corte, se predice desde el corte y se
compara con lo que pasó. Se mide contra dos referencias: «no cambia nada» y
«vuelve a su media de 12 meses». Si el modelo no las mejora, el índice lo dice.

Lo que no es
------------
No sabe qué va a decidir la empresa. Las acciones son contrafactuales: el
propio motor da el score con el pilar en su objetivo (`plan_actions`) y el
modelo predice desde ese punto, con una rampa del tiempo que tarda cada pilar
en notarse. Los escenarios «si sigue la deriva» y «si se repite su peor
trimestre» no son predicciones: son extrapolaciones explícitas, para
preguntarse qué pasaría si.

Todo es determinista: el mismo panel y los mismos parámetros dan los mismos
ficheros.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from . import panel as panel_module
from .actions import plan_actions
from .aggregate import aggregate
from .params import Params
from .pillars import compute_pillars

SCHEMA = "rumbo-horizons-v2"
INDEX_SCHEMA = "rumbo-horizons-index-v2"
PASADOS_SCHEMA = "rumbo-horizons-pasados-v2"
MODEL_VERSION = "forecast-v1"
H = 12
TAUS = (0.10, 0.25, 0.50, 0.75, 0.90)
QKEYS = ("p10", "p25", "p50", "p75", "p90")
PILLARS = ("liquidity", "payments", "collections", "activity", "debt")
BAND_KEYS = ("critical", "watch", "stable", "solid")
N_GRAINS = 40  # trayectorias de arena del corte actual
N_GRAINS_PASADO = 24  # y de cada corte pasado
LAMBDA = 2.0  # cresta sobre coeficientes estandarizados, a un mes


def cresta(h: int) -> float:
    """Más regularización cuanto más lejos: hay menos pares y el futuro lejano se parece menos
    al pasado reciente. Elegida con la validación (mejora a «no cambia nada» hasta 10 meses)."""
    return LAMBDA * (1 + h ** 3 / 8)
MIN_PARES = 150  # pares mínimos para entrenar un horizonte
CAL_CORTES = 3  # meses finales del entrenamiento que calibran los cuantiles

FEATURES = (
    "constante", "score", "score al cuadrado",
    "liquidez", "pagos", "cobros", "actividad", "deuda",
    "sin liquidez", "sin pagos", "sin cobros", "sin actividad", "sin deuda",
    "cambio en 1 mes", "cambio en 3 meses", "cambio en 6 meses",
    "pendiente de 12 meses", "volatilidad de 12 meses", "distancia a su media de 12 meses",
    "es empresa", "con tope",
)
# Fuera a propósito: los meses observados, la confianza y el tamaño. En la validación
# cambian de distribución entre los cortes de entrenamiento (entidades recién llegadas)
# y los de previsión, y el modelo los extrapolaba mal a partir de 7 meses.
NF = len(FEATURES)


def mindex(value) -> int:
    if isinstance(value, str):
        y, m = value.split("-")[:2]
        return int(y) * 12 + int(m) - 1
    return value.year * 12 + value.month - 1


def mlabel(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def tenths(score: float) -> int:
    return round(min(100.0, max(0.0, score)) * 10)


# --------------------------------------------------------------------------
# historia por entidad
# --------------------------------------------------------------------------


@dataclass
class Historia:
    kind: str
    eid: str
    group_id: str
    first: int  # índice del primer mes
    s: np.ndarray  # (T,) score en puntos; nan si no es vivo
    pil: np.ndarray  # (T, 5) pilares en puntos; nan si no hay
    conf: np.ndarray
    mo: np.ndarray
    capped: np.ndarray
    size: list[str]

    def pos(self, month: int) -> int:
        return month - self.first

    def vivo(self, month: int) -> bool:
        i = self.pos(month)
        return 0 <= i < len(self.s) and not math.isnan(self.s[i])


def historias(scores: pl.DataFrame) -> dict[str, Historia]:
    """scores.parquet del motor → una historia densa por entidad (meses sin fila = nan)."""
    out: dict[str, Historia] = {}
    df = scores.select([
        "entity_kind", "entity_id", "group_id", "month", "score", "feed_live", "abstained",
        "pillars", "confidence", "months_observed", "cap_adjustment", "size_band",
    ]).sort(["entity_id", "month"])
    for (eid,), g in df.group_by(["entity_id"], maintain_order=True):
        rows = g.to_dicts()
        first = mindex(rows[0]["month"])
        T = mindex(rows[-1]["month"]) - first + 1
        s = np.full(T, np.nan)
        pil = np.full((T, len(PILLARS)), np.nan)
        conf = np.full(T, np.nan)
        mo = np.zeros(T)
        capped = np.zeros(T)
        size = ["micro"] * T
        for r in rows:
            i = mindex(r["month"]) - first
            if r["feed_live"] and not r["abstained"] and r["score"] is not None:
                s[i] = float(r["score"])
            for k, p in enumerate(PILLARS):
                v = (r["pillars"] or {}).get(p)
                if v is not None:
                    pil[i, k] = float(v)
            conf[i] = float(r["confidence"] or 0.0)
            mo[i] = float(r["months_observed"] or 0)
            capped[i] = 1.0 if (r["cap_adjustment"] or 0) > 0 else 0.0
            size[i] = r["size_band"] or "micro"
        out[eid] = Historia(rows[0]["entity_kind"], eid, rows[0]["group_id"] or eid, first, s, pil, conf, mo, capped, size)
    return out


def variables(hi: Historia, month: int, s_override: float | None = None, pil_override: dict[str, float] | None = None) -> np.ndarray | None:
    """Las variables del corte, solo con lo que se sabía en ese mes. `s_override` y
    `pil_override` sirven para las acciones: el mismo corte con el score y un pilar movidos."""
    i = hi.pos(month)
    if i < 0 or i >= len(hi.s) or math.isnan(hi.s[i]):
        return None
    s = (s_override if s_override is not None else hi.s[i]) / 100.0
    x = np.zeros(NF)
    x[0] = 1.0
    x[1] = s
    x[2] = s * s
    for k, p in enumerate(PILLARS):
        v = pil_override.get(p) if pil_override and p in pil_override else hi.pil[i, k]
        if v is None or math.isnan(v):
            x[3 + k] = s
            x[8 + k] = 1.0
        else:
            x[3 + k] = v / 100.0
    real = hi.s[i] / 100.0

    def atras(k: int) -> float:
        j = i - k
        return 0.0 if j < 0 or math.isnan(hi.s[j]) else real - hi.s[j] / 100.0

    x[13], x[14], x[15] = atras(1), atras(3), atras(6)
    ventana = hi.s[max(0, i - 11): i + 1] / 100.0
    meses = np.arange(len(ventana), dtype=float)
    ok = ~np.isnan(ventana)
    if ok.sum() >= 3:
        mm, vv = meses[ok], ventana[ok]
        x[16] = float(np.polyfit(mm, vv, 1)[0])
        dif = np.diff(vv)
        x[17] = float(np.std(dif)) if len(dif) >= 2 else 0.1
        media = float(np.mean(vv))
    else:
        x[17] = 0.1
        media = real
    x[18] = s - media
    x[19] = 1.0 if hi.kind == "company" else 0.0
    x[20] = hi.capped[i]
    return x


# --------------------------------------------------------------------------
# el modelo
# --------------------------------------------------------------------------


@dataclass
class Modelo:
    h: int
    mu: np.ndarray  # medias de estandarización
    sd: np.ndarray
    beta: np.ndarray  # mediana del cambio (puntos), sobre variables estandarizadas
    gamma: np.ndarray  # escala (puntos)
    piso: float
    qz: np.ndarray  # multiplicadores de cada cuantil
    n: int
    n_cal: int

    def estandarizar(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sd
        Z[:, 0] = 1.0
        return Z

    def predecir(self, X: np.ndarray, s0: np.ndarray) -> np.ndarray:
        """(n, NF) variables y score del corte (puntos) → (n, 5) cuantiles en puntos."""
        Z = self.estandarizar(X)
        med = Z @ self.beta
        esc = np.maximum(Z @ self.gamma, self.piso)
        q = s0[:, None] + med[:, None] + self.qz[None, :] * esc[:, None]
        return np.sort(np.clip(q, 0.0, 100.0), axis=1)

    def aportes(self, x: np.ndarray) -> list[tuple[str, float]]:
        """Qué empuja la mediana del cambio para una entidad (puntos por variable)."""
        z = self.estandarizar(x[None, :])[0]
        return [(FEATURES[k], float(z[k] * self.beta[k])) for k in range(1, NF)]


def _cresta(Z: np.ndarray, y: np.ndarray, w: np.ndarray | None, lam: float) -> np.ndarray:
    D = np.eye(Z.shape[1]) * lam
    D[0, 0] = 0.0
    if w is None:
        A, b = Z.T @ Z, Z.T @ y
    else:
        Zw = Z * w[:, None]
        A, b = Zw.T @ Z, Zw.T @ y
    return np.linalg.solve(A + D, b)


def _mediana(Z: np.ndarray, y: np.ndarray, lam: float, vueltas: int = 40) -> np.ndarray:
    beta = _cresta(Z, y, None, lam)
    for _ in range(vueltas):
        r = y - Z @ beta
        w = 1.0 / np.maximum(np.abs(r), 0.5)
        nuevo = _cresta(Z, y, w / w.mean(), lam)
        if np.max(np.abs(nuevo - beta)) < 1e-6:
            beta = nuevo
            break
        beta = nuevo
    return beta


def entrenar(h: int, X: np.ndarray, y: np.ndarray, cortes: np.ndarray) -> Modelo | None:
    """X (n, NF), y cambio en puntos, cortes = mes de corte de cada par."""
    if len(y) < MIN_PARES:
        return None
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-9] = 1.0
    mu[0], sd[0] = 0.0, 1.0

    def ajustar(Xa: np.ndarray, ya: np.ndarray):
        Z = (Xa - mu) / sd
        Z[:, 0] = 1.0
        beta = _mediana(Z, ya, cresta(h))
        a = np.abs(ya - Z @ beta)
        gamma = _cresta(Z, a, None, cresta(h))
        piso = max(0.5, float(np.percentile(a, 10)))
        return beta, gamma, piso

    # Calibración: los últimos meses de corte del entrenamiento no entran en el ajuste.
    unicos = np.unique(cortes)
    cal = cortes >= unicos[-CAL_CORTES] if len(unicos) > CAL_CORTES + 2 else np.zeros(len(y), dtype=bool)
    if cal.sum() >= 60 and (~cal).sum() >= MIN_PARES:
        beta, gamma, piso = ajustar(X[~cal], y[~cal])
        Zc = (X[cal] - mu) / sd
        Zc[:, 0] = 1.0
        z = (y[cal] - Zc @ beta) / np.maximum(Zc @ gamma, piso)
        n_cal = int(cal.sum())
    else:
        beta, gamma, piso = ajustar(X, y)
        Z = (X - mu) / sd
        Z[:, 0] = 1.0
        z = (y - Z @ beta) / np.maximum(Z @ gamma, piso)
        n_cal = 0
    qz = np.quantile(z, TAUS)
    qz[2] = 0.0 if abs(qz[2]) < 1e-9 else qz[2]
    beta, gamma, piso = ajustar(X, y)
    return Modelo(h, mu, sd, beta, gamma, piso, qz, len(y), n_cal)


class Pares:
    """Todos los pares (entidad, corte, h) posibles, con sus variables calculadas una sola vez."""

    def __init__(self, hs: dict[str, Historia]):
        self.hs = hs
        filas, ids, cortes, s0 = [], [], [], []
        for eid, hi in hs.items():
            for i in range(len(hi.s)):
                m = hi.first + i
                x = variables(hi, m)
                if x is None:
                    continue
                filas.append(x)
                ids.append(eid)
                cortes.append(m)
                s0.append(hi.s[i])
        self.X = np.array(filas)
        self.ids = np.array(ids)
        self.cortes = np.array(cortes)
        self.s0 = np.array(s0)
        # objetivo a cada horizonte: score vivo en t + h (nan si no)
        self.Y = np.full((len(ids), H), np.nan)
        for n, (eid, m) in enumerate(zip(ids, cortes)):
            hi = hs[eid]
            for h in range(1, H + 1):
                j = hi.pos(m + h)
                if 0 <= j < len(hi.s):
                    self.Y[n, h - 1] = hi.s[j]

    def modelos(self, hasta: int) -> dict[int, Modelo]:
        """Un modelo por horizonte con los pares cuyo mes objetivo es ≤ `hasta` (nada del futuro)."""
        out = {}
        for h in range(1, H + 1):
            sel = (~np.isnan(self.Y[:, h - 1])) & (self.cortes + h <= hasta)
            m = entrenar(h, self.X[sel], self.Y[sel, h - 1] - self.s0[sel], self.cortes[sel])
            if m is None:
                break  # sin pares para este horizonte, tampoco para los siguientes
            out[h] = m
        return out


# --------------------------------------------------------------------------
# de cuantiles a arena, bandas y cruce
# --------------------------------------------------------------------------


def _cuantil(q: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Función cuantil lineal a trozos por (τ, q), con colas prolongadas hasta 2 % y 98 %."""
    t = np.array([0.02, *TAUS, 0.98])
    lo = q[0] - (q[1] - q[0]) * (TAUS[0] - 0.02) / (TAUS[1] - TAUS[0])
    hi = q[-1] + (q[-1] - q[-2]) * (0.98 - TAUS[-1]) / (TAUS[-1] - TAUS[-2])
    v = np.array([lo, *q, hi])
    return np.clip(np.interp(u, t, v), 0.0, 100.0)


def _cdf(q: np.ndarray, x: float) -> float:
    t = np.array([0.02, *TAUS, 0.98])
    lo = q[0] - (q[1] - q[0]) * (TAUS[0] - 0.02) / (TAUS[1] - TAUS[0])
    hi = q[-1] + (q[-1] - q[-2]) * (0.98 - TAUS[-1]) / (TAUS[-1] - TAUS[-2])
    v = np.maximum.accumulate(np.array([lo, *q, hi]))
    if x <= v[0]:
        return 0.0
    if x >= v[-1]:
        return 1.0
    return float(np.interp(x, v, t))


def abanico(Q: np.ndarray, months: list[str], shown: int, mins: list[int], n_granos: int) -> dict:
    """Q (h, 5) en puntos → cuantiles en décimas, probabilidad de cada banda, primer cruce
    de banda y granos de arena: n trayectorias comonótonas (cada una sigue su propio cuantil)."""
    nh = Q.shape[0]
    q = {k: [tenths(Q[h, j]) for h in range(nh)] for j, k in enumerate(QKEYS)}
    cortes_b = [m / 10.0 for m in mins] + [100.01]
    ahora = int(np.searchsorted(np.array(mins), shown, side="right") - 1)

    def prob_bandas(h: int) -> list[float]:
        F = [_cdf(Q[h], c) for c in cortes_b[1:]]
        p = [F[0]] + [F[b] - F[b - 1] for b in range(1, 4)]
        return [max(0.0, x) for x in p]

    bands = {}
    for nombre, hh in (("h3", 3), ("h6", 6), ("h12", 12)):
        if hh <= nh:
            p = prob_bandas(hh - 1)
            bands[nombre] = {BAND_KEYS[b]: round(p[b], 2) for b in range(4)}
    cross = None
    for h in range(nh):
        p = prob_bandas(h)
        down, up = sum(p[:ahora]), sum(p[ahora + 1:])
        if down >= 0.5 or up >= 0.5:
            peor = down >= 0.5
            rango = range(0, ahora) if peor else range(ahora + 1, 4)
            to = max(rango, key=lambda b: p[b])
            cross = {"dir": "down" if peor else "up", "to": BAND_KEYS[to], "month": months[h], "prob": round(down if peor else up, 2)}
            break
    # n trayectorias: la n-ésima sigue su cuantil (n + 0,5) / N con una leve ondulación
    # determinista, para que no sean paralelas.
    nn = np.arange(n_granos)[:, None]
    hh = np.arange(nh)[None, :]
    U = np.clip((nn + 0.5) / n_granos + 0.06 * np.sin(1.7 * nn + 0.9 * hh), 0.02, 0.98)
    V = np.column_stack([_cuantil(Q[h], U[:, h]) for h in range(nh)]) if nh else np.zeros((n_granos, 0))
    grains = [[h + 1, tenths(float(V[n, h]))] for n in range(n_granos) for h in range(nh)]
    return {"q": q, "bands": bands, "cross": cross, "grains": grains}


def _cruce_linea(p50: list[int], months: list[str], shown: int, mins: list[int]) -> dict | None:
    ahora = int(np.searchsorted(np.array(mins), shown, side="right") - 1)
    for h, v in enumerate(p50):
        b = int(np.searchsorted(np.array(mins), v, side="right") - 1)
        if b != ahora:
            return {"dir": "down" if b < ahora else "up", "to": BAND_KEYS[b], "month": months[h], "prob": None}
    return None


# --------------------------------------------------------------------------
# acciones del motor en el corte
# --------------------------------------------------------------------------


def retardos(P: Params) -> dict[str, int]:
    """Meses que tarda cada pilar en notarse: su ventana de medida en los parámetros."""
    return {
        "liquidity": 1,  # caja a fin de mes y líneas sin disponer: un saldo
        "payments": max(1, round(P.invoices.window_days / 30)),
        "collections": max(1, round(P.invoices.window_days / 30)),
        "activity": P.activity.coverage_window_months,
        "debt": P.debt.window_months,
    }


def acciones_en_corte(panel: pl.DataFrame, P: Params, corte: int) -> dict[str, dict]:
    """Para cada entidad, el plan de acciones del motor en el corte y el score de cada combinación."""
    mes = panel.filter(pl.col("month").dt.year() * 12 + pl.col("month").dt.month() - 1 == corte)
    filas = list(panel_module.iter_rows(mes))
    grupos = {r.entity_id: r for r in filas if r.entity_kind == "group"}
    out = {}
    for row in filas:
        gr = grupos.get(row.group_id) if row.entity_kind == "company" else None
        pillars = compute_pillars(row, P, gr)
        parts = aggregate(pillars, row, P, gr)
        plan = plan_actions(row, pillars, parts, P, gr)
        combos = []
        for size in range(2, len(plan.actions) + 1):
            for sub in itertools.combinations(plan.actions, size):
                cambiado = dict(pillars)
                for a in sub:
                    cambiado[a.pillar] = replace(pillars[a.pillar], score=a.pillar_target)
                combos.append({"ids": sorted(a.id for a in sub), "new_score": tenths(aggregate(cambiado, row, P, gr).score)})
        out[row.entity_id] = {"shown": tenths(parts.score), "actions": plan.actions, "combos": combos}
    return out


# --------------------------------------------------------------------------
# validación
# --------------------------------------------------------------------------


def validar(pares: Pares, cortes_val: list[int], ultimo: int) -> dict:
    """Origen móvil: en cada corte, se entrena con lo anterior y se compara con lo que pasó."""
    por_h: dict[int, dict[str, list]] = {h: {"err": [], "naive": [], "media": [], "c50": [], "c80": []} for h in range(1, H + 1)}
    feb: dict[str, list] = {"err": [], "naive": [], "c80": []}
    for c in cortes_val:
        mods = pares.modelos(c)
        sel = pares.cortes == c
        for h, m in mods.items():
            if c + h > ultimo:
                continue
            ok = sel & ~np.isnan(pares.Y[:, h - 1])
            if not ok.any():
                continue
            Q = m.predecir(pares.X[ok], pares.s0[ok])
            real = pares.Y[ok, h - 1]
            err = np.abs(Q[:, 2] - real)
            naive = np.abs(pares.s0[ok] - real)
            media = np.abs((pares.s0[ok] / 100.0 - pares.X[ok, 18]) * 100.0 - real)
            c50 = (Q[:, 1] <= real) & (real <= Q[:, 3])
            c80 = (Q[:, 0] <= real) & (real <= Q[:, 4])
            if h in por_h:
                d = por_h[h]
                d["err"] += err.tolist(); d["naive"] += naive.tolist(); d["media"] += media.tolist()
                d["c50"] += c50.tolist(); d["c80"] += c80.tolist()
            if c == ultimo - 6 and h in (3, 6):
                feb["err"] += err.tolist(); feb["naive"] += naive.tolist(); feb["c80"] += c80.tolist()
    res = {}
    for h, d in por_h.items():
        if not d["err"]:
            continue
        res[f"h{h}"] = {
            "n": len(d["err"]),
            "error_mediana": round(float(np.mean(d["err"])), 2),
            "error_sin_cambio": round(float(np.mean(d["naive"])), 2),
            "error_media_12": round(float(np.mean(d["media"])), 2),
            "acierta_50": round(float(np.mean(d["c50"])), 3),
            "acierta_80": round(float(np.mean(d["c80"])), 3),
        }
    # hasta dónde está validado: el último horizonte con al menos 300 casos fuera de muestra
    validados = [h for h in range(1, H + 1) if res.get(f"h{h}", {}).get("n", 0) >= 300]
    out = {"cortes": [mlabel(c) for c in cortes_val], "por_horizonte": res, "unidades": "puntos (0-100)",
           "validado_hasta": max(validados) if validados else 0}
    if feb["err"]:
        out["corte_de_referencia"] = {
            "corte": mlabel(ultimo - 6), "horizontes": [3, 6], "n": len(feb["err"]),
            "error_mediana": round(float(np.mean(feb["err"])), 2),
            "error_sin_cambio": round(float(np.mean(feb["naive"])), 2),
            "acierta_80": round(float(np.mean(feb["c80"])), 3),
        }
    return out


# --------------------------------------------------------------------------
# escritura
# --------------------------------------------------------------------------


def _json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))


def _predecir_una(mods: dict[int, Modelo], x: np.ndarray, s0: float) -> np.ndarray:
    return np.vstack([mods[h].predecir(x[None, :], np.array([s0]))[0] for h in sorted(mods)])


def prever(
    artifacts: Path,
    bundle: Path,
    params: Params,
    out_dir: Path,
    pasados: tuple[int, int] | None = None,
    log=print,
) -> dict:
    """Entrena, valida y escribe horizons/<id>.json (el corte actual), horizons/pasados/<id>.json
    (el futuro visto desde cada corte pasado, siempre fuera de muestra) y horizons/index.json."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    mins = [b["min"] for b in manifest["bands"]]
    assert [b["key"] for b in manifest["bands"]] == list(BAND_KEYS)
    scores = pl.read_parquet(artifacts / "scores.parquet")
    hs = historias(scores)
    pares = Pares(hs)
    ultimo = int(pares.cortes.max())
    log(f"{len(hs)} entidades, {len(pares.ids)} meses vivos, corte {mlabel(ultimo)}")

    # 1. validación fuera de muestra
    cortes_val = [c for c in range(ultimo - 12, ultimo) if c >= ultimo - 12]
    val = validar(pares, cortes_val, ultimo)
    log(f"validación: {json.dumps(val['por_horizonte'])}")

    # 2. el modelo de producción: todo lo que se sabe hasta el corte
    mods = pares.modelos(ultimo)
    lags = retardos(params)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = acciones_en_corte(pl.read_parquet(artifacts / "panel.parquet"), params, ultimo)
    months = [mlabel(ultimo + h) for h in range(1, H + 1)]
    resumen, checks = {}, {"reproduce_corte": [0, 0], "acciones_como_el_bundle": [0, 0]}
    for eid, hi in hs.items():
        sub = "companies" if hi.kind == "company" else "groups"
        doc = json.loads((bundle / sub / f"{eid}.json").read_text(encoding="utf-8"))
        entry = next((m for m in doc["months"] if m["month"] == mlabel(ultimo)), None)
        head = {"schema": SCHEMA, "entity_id": eid, "entity_kind": hi.kind, "group_id": hi.group_id,
                "cut": mlabel(ultimo), "bundle_id": manifest["bundle_id"], "params_hash": manifest["params_hash"],
                "months": months, "model": {"version": MODEL_VERSION, "trained_until": mlabel(ultimo)}}
        x = variables(hi, ultimo)
        if x is None or entry is None or entry["abstain"] is not None or not entry["feed_live"]:
            razon = ("stale_feed" if entry and not entry["feed_live"] else entry["abstain"]["reason"] if entry and entry["abstain"] else "missing")
            _json(out_dir / f"{eid}.json", {**head, "shown_at_cut": entry["shown"] if entry else None, "scenarios": None,
                                            "reason_code": razon, "actions": [], "combos": []})
            resumen[eid] = {"kind": hi.kind, "p50_h6": None, "p_critical_h6": None, "cross": None, "shown_at_cut": entry["shown"] if entry else None}
            continue
        shown = entry["shown"]
        Q = _predecir_una(mods, x, hi.s[hi.pos(ultimo)])
        base = abanico(Q, months, shown, mins, N_GRAINS)
        # qué pasaría si: extrapolaciones explícitas, no predicciones
        pend = x[16] * 100.0
        drift = [tenths(hi.s[hi.pos(ultimo)] + pend * h) for h in range(1, H + 1)]
        ventana = hi.s[max(0, hi.pos(ultimo) - 11): hi.pos(ultimo) + 1]
        caidas = [ventana[j + 3] - ventana[j] for j in range(len(ventana) - 3) if not (math.isnan(ventana[j]) or math.isnan(ventana[j + 3]))]
        peor = min([0.0, *caidas])
        stress = [tenths(Q[h, 2] + peor * min(1.0, (h + 1) / 3)) for h in range(H)]
        scen = {
            "base": base,
            "drift": {"q": {"p50": drift}, "cross": _cruce_linea(drift, months, shown, mins), "what_if": True},
            "stress": {"q": {"p50": stress}, "cross": _cruce_linea(stress, months, shown, mins), "what_if": True, "worst_quarter": round(peor, 1)},
        }
        # acciones: el motor da el punto de llegada; el modelo predice desde él
        p = plan.get(eid)
        acciones = []
        if p:
            checks["reproduce_corte"][1] += 1
            checks["reproduce_corte"][0] += int(abs(p["shown"] - shown) <= 1)
            ids_bundle = sorted(a["id"] for a in entry.get("actions", []))
            checks["acciones_como_el_bundle"][1] += 1
            checks["acciones_como_el_bundle"][0] += int(ids_bundle == sorted(a.id for a in p["actions"]))
            for a in p["actions"]:
                nuevo = tenths(a.new_score)
                xm = variables(hi, ultimo, s_override=nuevo / 10.0, pil_override={a.pillar: a.pillar_target})
                Qm = _predecir_una(mods, xm, nuevo / 10.0)
                L = lags[a.pillar]
                w = np.minimum(1.0, np.arange(1, Q.shape[0] + 1) / L)[:, None]
                Qa = np.sort(Q + w * (Qm - Q), axis=1)
                acciones.append({"id": a.id, "pillar": a.pillar, "lag_months": L, "current": round(a.current, 4), "target": round(a.target, 4),
                                 "engine_new_score": nuevo, **abanico(Qa, months, shown, mins, N_GRAINS),
                                 "in_bundle": a.id in ids_bundle})
        # por qué: lo que empuja la mediana a seis meses
        explica = sorted(mods[min(6, max(mods))].aportes(x), key=lambda t: -abs(t[1]))[:5] if mods else []
        _json(out_dir / f"{eid}.json", {**head, "shown_at_cut": shown, "scenarios": scen, "actions": acciones,
                                        "combos": p["combos"] if p else [],
                                        "explain_h6": [{"variable": k, "points": round(v, 1)} for k, v in explica]})
        cdf_crit = _cdf(Q[min(5, Q.shape[0] - 1)], mins[1] / 10.0) if Q.shape[0] else None
        resumen[eid] = {"kind": hi.kind, "p50_h6": base["q"]["p50"][5] if Q.shape[0] > 5 else None,
                        "p_critical_h6": round(cdf_crit, 2) if cdf_crit is not None else None,
                        "cross": base["cross"], "shown_at_cut": shown}
    log(f"corte {mlabel(ultimo)}: {sum(1 for r in resumen.values() if r['p50_h6'] is not None)} entidades con previsión")

    # 3. los cortes pasados, cada uno con un modelo que solo sabe lo anterior
    cortes_pasados: list[str] = []
    if pasados:
        dest = out_dir / "pasados"
        dest.mkdir(parents=True, exist_ok=True)
        porcorte: dict[str, dict[str, dict]] = {eid: {} for eid in hs}
        for c in range(pasados[0], min(pasados[1], ultimo - 1) + 1):
            mc = pares.modelos(c)
            if not mc:
                continue
            cortes_pasados.append(mlabel(c))
            mths = [mlabel(c + h) for h in range(1, len(mc) + 1)]
            for eid, hi in hs.items():
                x = variables(hi, c)
                if x is None:
                    continue
                s0 = hi.s[hi.pos(c)]
                Qc = _predecir_una(mc, x, s0)
                ab = abanico(Qc, mths, tenths(s0), mins, N_GRAINS_PASADO)
                porcorte[eid][mlabel(c)] = {"months": mths, "shown_at_cut": tenths(s0), "q": ab["q"], "grains": ab["grains"], "trained_until": mlabel(c)}
            log(f"pasado {mlabel(c)}: {len(mc)} horizontes")
        for eid, cuts in porcorte.items():
            _json(dest / f"{eid}.json", {"schema": PASADOS_SCHEMA, "entity_id": eid, "bundle_id": manifest["bundle_id"], "cuts": cuts})

    # 4. el índice: el modelo, su validación y lo que pesa cada variable
    coef = {}
    for h in (3, 6, 12):
        if h in mods:
            m = mods[h]
            coef[f"h{h}"] = {FEATURES[k]: round(float(m.beta[k]), 3) for k in range(NF)}
    index = {
        "schema": INDEX_SCHEMA, "cut": mlabel(ultimo), "bundle_id": manifest["bundle_id"], "params_hash": manifest["params_hash"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": {
            "version": MODEL_VERSION,
            "type": "regresión cuantílica lineal por horizonte (mediana) con escala propia y calibración conformal en el tiempo",
            "target": "cambio del score entre el corte y el mes h (puntos)",
            "features": list(FEATURES), "horizons": sorted(mods), "ridge_lambda": {f"h{h}": round(cresta(h), 2) for h in sorted(mods)},
            "train_pairs": {f"h{h}": m.n for h, m in mods.items()}, "calibration_pairs": {f"h{h}": m.n_cal for h, m in mods.items()},
            "quantile_multipliers": {f"h{h}": [round(float(v), 3) for v in m.qz] for h, m in mods.items()},
            "lags": lags, "what_if": {"drift": "pendiente de 12 meses prolongada", "stress": "la mediana menos la peor caída de 3 meses del último año, en tres meses"},
        },
        "validation": val,
        "coefficients": coef,
        "checks": {k: f"{v[0]}/{v[1]}" for k, v in checks.items()},
        "past_cuts": cortes_pasados,
        "entities": resumen,
    }
    _json(out_dir / "index.json", index)
    log(f"comprobaciones: {index['checks']}")
    return index
