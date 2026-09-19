"""Qué productos financieros tiene contratados cada empresa, leído de los datos del reto.

Fuentes (copias parquet de los CSV del reto):
  - debt_products: líneas de crédito, factoring, confirming y el resto de deudas (préstamos,
    leasing, avales, hipotecas, renting), con concedido, dispuesto y disponible.
  - debt_schedule_config: tipo de interés, plazos y próxima cuota de 87 productos.
  - banking_products: cuentas de ahorro (cuenta remunerada) y de inversión (depósitos).
  - transactions: lo que no está declarado pero se ve en los movimientos de los últimos 12 meses.

Reglas deducidas de movimientos (medidas sobre el dataset real; ver --informe):
  - factoring: solo señales explícitas de un contrato de factoring propio (financiación,
    operación, intereses o comisiones de factoring). Los abonos de «Santander Factoring y
    Confirming» NO cuentan: esa entidad también paga confirming de clientes, así que son
    ambiguos; se guardan como señal informativa.
  - confirming: comisiones de emisión, gestión, renovación o prórroga de confirming que paga la
    propia empresa. Los «anticipos de confirming» que cobra son el confirming de sus clientes:
    señal informativa, no producto propio.
  - seguro de crédito: recibos pagados a aseguradoras de crédito (CESCE, Coface, Solunion,
    Atradius, Crédito y Caución, Allianz Trade). Los cobros de esas entidades no cuentan.
  - cuenta remunerada: intereses acreedores abonados en cuenta en al menos 2 meses distintos.
    Los intereses cargados (descubiertos) no cuentan.
  - depósitos y letras: constituciones o intereses de imposiciones a plazo y letras del Tesoro.
  - plan de pensiones: no aparece en los datos; la regla se deja escrita y no encuentra nada.

Nada se inventa: donde el dato no existe, el campo es null. Los importes van en euros, en
positivo (el dataset los trae en negativo), convertidos con la tabla de cambio fija del motor.
`since` es la fecha en que el producto se conectó a la plataforma, no la del contrato.

Uso:
  uv run --no-project --with polars --with pyarrow python scripts/datos/productos.py \
      --parquet ~/Developer/hackspain-data/parquet --raw ~/Developer/hackspain-data/raw \
      --params ~/Developer/hackspain-motor/params/reference_v1.json \
      --out ~/Developer/hackspain-data/rumbo/products --cut 2026-08
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

PRODUCTOS = ["linea_credito", "factoring", "confirming", "seguro_credito", "cuenta_remunerada", "depositos", "plan_pensiones"]
DEUDA_A_PRODUCTO = {"lineofcredit": "linea_credito", "factoring": "factoring", "confirming": "confirming"}
OTRAS = {"loan": "Préstamo", "leasing": "Leasing", "guarantee": "Aval", "mortgage": "Hipoteca", "renting": "Renting"}
TIPO_INTERES = {"fixed": "fijo", "variable": "variable"}

REGLAS = {
    "factoring": {
        "patron": r"FINANCIACION\s+FACTORING|OPERACION\s+DE\s+FACTORING|FACTORING\s+LIQUID|INTERESES\s+ANTICIPO\s+FACTORING|FACTORING:\s*S\.DEUDOR|FACTORING\s+COBRO\s+COMISI|ANTICIPO\s+(DE\s+)?FACTURAS",
        "signo": "cualquiera",
        "nota": "Financiación, operaciones, intereses y comisiones de factoring propios.",
    },
    "confirming": {
        "patron": r"CONFIRMING",
        "signo": "salida",
        "nota": "Comisiones de confirming que paga la propia empresa.",
    },
    "seguro_credito": {
        "patron": r"\b(CESCE|COFACE|SOLUNION|ATRADIUS|CREDITO\s+Y\s+CAUCION|CRÉDITO\s+Y\s+CAUCIÓN|ALLIANZ\s+TRADE)\b",
        "signo": "salida",
        "nota": "Recibos pagados a aseguradoras de crédito.",
    },
    "cuenta_remunerada": {
        "patron": r"INTERES(ES)?\s+(ACREEDOR|ABONAD|A\s+SU\s+FAVOR)|ABONO\s+(DE\s+)?INTERES|INTEREST\s+PAID|REMUNERACI[OÓ]N\s+(DE\s+)?CUENTA",
        "signo": "entrada",
        "meses_min": 2,
        "nota": "Intereses acreedores abonados en cuenta, en al menos 2 meses.",
    },
    "depositos": {
        "patron": r"PLAZO\s+FIJO|\bIMPOSICI[OÓ]N\b|DEP\.?\s*PLAZO|DEP[OÓ]SITO\s+A\s+PLAZO|LETRAS?\s+(DEL\s+)?TESORO|CONST\.?\s+.{0,40}\bPLAZO\b",
        "signo": "cualquiera",
        "nota": "Imposiciones a plazo y letras del Tesoro.",
    },
    "plan_pensiones": {
        "patron": r"PLAN(ES)?\s+DE\s+PENSIONES|\bEPSV\b|PLAN\s+DE\s+PREVISI[OÓ]N\s+SOCIAL",
        "signo": "salida",
        "nota": "Aportaciones a planes de pensiones o EPSV. No aparece ninguna en el dataset.",
    },
}
SENALES = {
    "cobra_por_confirming": (r"ANTICIPO\s+\S*CONFIRMING", "entrada", "Cobra de sus clientes a través del confirming de ellos."),
    "cobra_de_entidad_factoring": (r"SANTANDER\s+FACTORING", "entrada", "Recibe abonos de una entidad de factoring y confirming (ambiguo: puede ser confirming de un cliente)."),
}

LIMPIAR = [(r"COUNTERPARTY_\d+", ""), (r"\[(NUM|REF|COMPANY|TAXID|X)\]", ""), (r"DOCNUM:\S*", ""), (r"\d[\d\-\.]{5,}", ""), (r"\s{2,}", " ")]


def limpiar(texto: str) -> str:
    t = texto or ""
    for p, r in LIMPIAR:
        t = re.sub(p, r, t)
    t = t.strip(" ,.-/")
    return (t[:40] + "…") if len(t) > 40 else t


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cut", default="2026-08")
    a = ap.parse_args()
    P = Path(a.parquet).expanduser()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    cut = a.cut
    anio, mes = map(int, cut.split("-"))
    fin = datetime(anio + (mes == 12), mes % 12 + 1, 1)
    # Ventana de 12 meses que acaba en el mes de corte: de (corte − 11) a corte, ambos incluidos.
    a0, m0 = (anio, mes - 11) if mes > 11 else (anio - 1, mes + 1)
    inicio = datetime(a0, m0, 1)

    params = json.loads(Path(a.params).expanduser().read_text())
    fx = params["fx"]["rates"]

    def eur(v, moneda):
        if v is None:
            return None
        r = fx.get(moneda or "EUR")
        return None if r is None else round(abs(float(v)) * r, 2)

    companies = pl.read_parquet(P / "companies.parquet").select(["company_id", "group_id"])
    grupo_de = dict(companies.iter_rows())
    deuda = pl.read_parquet(P / "debt_products.parquet").filter(pl.col("created_at") < fin)
    calendario = pl.read_parquet(P / "debt_schedule_config.parquet")
    banca = pl.read_parquet(P / "banking_products.parquet").filter(pl.col("created_at") < fin)
    saldos = pl.read_parquet(P / "balances.parquet")
    cal = {r["product_id"]: r for r in calendario.iter_rows(named=True)}
    saldo = {}
    for r in saldos.sort("date").iter_rows(named=True):
        saldo[r["product_id"]] = r

    # Movimientos de los 12 meses que acaban en el corte.
    t = (pl.read_parquet(P / "transactions.parquet", columns=["company_id", "date", "amount", "description"])
         .filter((pl.col("date") >= inicio) & (pl.col("date") < fin))
         .with_columns(pl.col("description").fill_null("").str.to_uppercase().alias("d"), pl.col("date").dt.strftime("%Y-%m").alias("mes")))

    def coincidencias(patron: str, signo: str) -> pl.DataFrame:
        m = t.filter(pl.col("d").str.contains(patron))
        if signo == "entrada":
            m = m.filter(pl.col("amount") > 0)
        elif signo == "salida":
            m = m.filter(pl.col("amount") < 0)
        return m

    inferido: dict[str, dict[str, dict]] = {p: {} for p in PRODUCTOS}
    medidas = {}
    for prod, regla in REGLAS.items():
        m = coincidencias(regla["patron"], regla["signo"])
        por = m.group_by("company_id").agg(
            pl.len().alias("filas"), pl.col("mes").min().alias("primero"), pl.col("mes").max().alias("ultimo"),
            pl.col("mes").n_unique().alias("meses"), pl.col("amount").abs().sum().alias("importe"),
            pl.col("description").head(2).alias("ejemplos"))
        if regla.get("meses_min"):
            por = por.filter(pl.col("meses") >= regla["meses_min"])
        for r in por.iter_rows(named=True):
            inferido[prod][r["company_id"]] = {
                "file": "transactions.csv", "rows": int(r["filas"]), "first": r["primero"], "last": r["ultimo"],
                "amount_12m": round(float(r["importe"]), 2), "examples": [limpiar(x) for x in r["ejemplos"]],
            }
        medidas[prod] = {"empresas": por.height, "filas": int(por["filas"].sum()) if por.height else 0}

    senales: dict[str, dict[str, dict]] = {}
    for clave, (patron, signo, nota) in SENALES.items():
        m = coincidencias(patron, signo)
        por = m.group_by("company_id").agg(pl.len().alias("filas"), pl.col("amount").abs().sum().alias("importe"))
        for r in por.iter_rows(named=True):
            senales.setdefault(r["company_id"], {})[clave] = {"texto": nota, "rows": int(r["filas"]), "amount_12m": round(float(r["importe"]), 2)}

    empresas = {}
    for cid, gid in grupo_de.items():
        empresas[cid] = {"schema": "rumbo-products-v1", "company_id": cid, "group_id": gid, "cut": cut,
                         "held": {}, "other_debt": [], "accounts": {}, "banks": {}, "signals": senales.get(cid, {}),
                         "totals": {"debt_granted": 0.0, "debt_outstanding": 0.0, "lines_granted": 0.0, "lines_available": 0.0}}

    # Deuda declarada.
    for r in deuda.iter_rows(named=True):
        e = empresas.get(r["company_id"])
        if e is None:
            continue
        moneda = r["currency"] or "EUR"
        concedido, dispuesto, disponible = eur(r["granted"], moneda), eur(r["outstanding"], moneda), eur(r["liquidity"], moneda)
        c = cal.get(r["product_id"])
        tipo = (c or {}).get("annual_interest_rate_or_spread")
        item = {
            "bank": r["bank_name"], "label": r["label"], "granted": concedido, "outstanding": dispuesto,
            "available": disponible if disponible is not None else (round(concedido - dispuesto, 2) if concedido is not None and dispuesto is not None and r["type"] == "lineofcredit" else None),
            "usage": round(dispuesto / concedido, 4) if concedido and dispuesto is not None else None,
            "since": r["created_at"].strftime("%Y-%m") if r["created_at"] else None,
            "rate": round(tipo * 100, 3) if tipo is not None else None,
            "rate_type": TIPO_INTERES.get((c or {}).get("interest_type")),
        }
        if moneda != "EUR":
            item["currency"] = moneda
        # Un dispuesto de más de vez y media el límite no es un uso: es un dato incoherente del origen.
        if item["usage"] is not None and item["usage"] > 1.5:
            item.update({"usage": None, "available": None, "inconsistent": True})
        prod = DEUDA_A_PRODUCTO.get(r["type"])
        if prod:
            h = e["held"].setdefault(prod, {"product": prod, "source": "declarado", "items": [], "evidence": []})
            h["items"].append(item)
            if prod == "linea_credito":
                e["totals"]["lines_granted"] += concedido or 0
                e["totals"]["lines_available"] += item["available"] or 0
        elif r["type"] in OTRAS:
            cerrado = (dispuesto or 0) == 0 and (concedido or 0) == 0
            e["other_debt"].append({
                "type": r["type"], "type_label": OTRAS[r["type"]], "bank": r["bank_name"], "label": r["label"],
                "granted": concedido, "outstanding": dispuesto, "rate": item["rate"], "rate_type": item["rate_type"],
                "periods": (c or {}).get("total_periods"),
                "next_payment": c["next_payment_date"].strftime("%Y-%m-%d") if c and c.get("next_payment_date") else None,
                "since": item["since"], "closed": cerrado,
            })
        if not (r["type"] in OTRAS and (dispuesto or 0) == 0 and (concedido or 0) == 0):
            e["totals"]["debt_granted"] += concedido or 0
            e["totals"]["debt_outstanding"] += dispuesto or 0

    # Cuentas declaradas: ahorro → cuenta remunerada; inversión → depósitos.
    for r in banca.iter_rows(named=True):
        e = empresas.get(r["company_id"])
        if e is None:
            continue
        tipo = r["type"]
        e["accounts"][tipo] = e["accounts"].get(tipo, 0) + 1
        if r["bank_name"]:
            e["banks"][r["bank_name"]] = e["banks"].get(r["bank_name"], 0) + 1
        prod = {"saving": "cuenta_remunerada", "investment": "depositos"}.get(tipo)
        if prod:
            s = saldo.get(r["product_id"])
            h = e["held"].setdefault(prod, {"product": prod, "source": "declarado", "items": [], "evidence": []})
            h["items"].append({"bank": r["bank_name"], "label": r["label"], "granted": None, "outstanding": None, "available": None,
                               "usage": None, "since": r["created_at"].strftime("%Y-%m") if r["created_at"] else None,
                               "rate": None, "rate_type": None,
                               "balance": eur(s["balance"], r["currency"]) if s and s["balance"] is not None else None})

    # Lo deducido de movimientos se añade como evidencia o como producto nuevo.
    for prod, por in inferido.items():
        for cid, ev in por.items():
            e = empresas.get(cid)
            if e is None:
                continue
            h = e["held"].get(prod)
            if h is None:
                e["held"][prod] = {"product": prod, "source": "movimientos", "items": [], "evidence": [ev]}
            else:
                h["evidence"].append(ev)
    for e in empresas.values():
        for h in e["held"].values():
            if h["source"] == "declarado":
                archivo = "debt_products.csv" if h["product"] in DEUDA_A_PRODUCTO.values() else "banking_products.csv"
                h["evidence"].insert(0, {"file": archivo, "rows": len(h["items"]), "first": None, "last": None, "amount_12m": None, "examples": []})
        e["held"] = [e["held"][p] for p in PRODUCTOS if p in e["held"]]
        e["totals"] = {k: round(v, 2) for k, v in e["totals"].items()}
        (out / f"{e['company_id']}.json").write_text(json.dumps(e, ensure_ascii=False, separators=(",", ":")))

    # Grupos e índice.
    grupos: dict[str, dict] = {}
    for e in empresas.values():
        g = grupos.setdefault(e["group_id"], {"schema": "rumbo-products-group-v1", "group_id": e["group_id"], "cut": cut, "companies": [], "counts": {}, "banks": {}, "totals": {}})
        g["companies"].append({"id": e["company_id"], "held": [h["product"] for h in e["held"]], "sources": {h["product"]: h["source"] for h in e["held"]}})
        for h in e["held"]:
            g["counts"][h["product"]] = g["counts"].get(h["product"], 0) + 1
        for banco, n in e["banks"].items():
            g["banks"][banco] = g["banks"].get(banco, 0) + n
        for k, v in e["totals"].items():
            g["totals"][k] = round(g["totals"].get(k, 0) + v, 2)
    for gid, g in grupos.items():
        g["companies"].sort(key=lambda c: c["id"])
        (out / f"{gid}.json").write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")))

    cartera = {}
    for p in PRODUCTOS:
        tienen = [e for e in empresas.values() if any(h["product"] == p for h in e["held"])]
        cartera[p] = {
            "companies": len(tienen),
            "groups": len({e["group_id"] for e in tienen}),
            "declared": sum(1 for e in tienen if any(h["product"] == p and h["source"] == "declarado" for h in e["held"])),
            "inferred": sum(1 for e in tienen if any(h["product"] == p and h["source"] == "movimientos" for h in e["held"])),
        }
    raw = Path(a.raw).expanduser()
    fuentes = {n: sha(raw / n) for n in ["debt_products.csv", "debt_schedule_config.csv", "banking_products.csv", "balances.csv", "transactions.csv", "companies.csv"] if (raw / n).exists()}
    indice = {
        "schema": "rumbo-products-index-v1", "cut": cut, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": [inicio.strftime("%Y-%m"), cut], "source_files": fuentes,
        "rules": {p: {"declared": {"linea_credito": "debt_products · lineofcredit", "factoring": "debt_products · factoring", "confirming": "debt_products · confirming",
                                   "cuenta_remunerada": "banking_products · saving", "depositos": "banking_products · investment"}.get(p),
                      "inferred": REGLAS.get(p, {}).get("patron"), "sign": REGLAS.get(p, {}).get("signo"),
                      "note": REGLAS.get(p, {}).get("nota"), "measured": medidas.get(p)} for p in PRODUCTOS},
        "signals": {k: {"pattern": v[0], "note": v[2]} for k, v in SENALES.items()},
        "portfolio": cartera,
        "groups": {gid: g["counts"] for gid, g in grupos.items()},
    }
    (out / "index.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1))
    print(json.dumps({"ventana": indice["window"], "cartera": cartera, "medidas": medidas}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
