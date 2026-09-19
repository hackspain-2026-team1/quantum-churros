"""Índice de empresas para Rumbo: tamaño, grupo y score de cada empresa en el mes de corte.

Sirve para situar a una empresa frente a las de su tamaño sin leer los 1.286 ficheros en el
navegador. Sale del bundle del motor (companies/<id>.json: perfil y meses); no calcula nada nuevo.
Solo stdlib.

Uso: python3 scripts/datos/indice.py --bundle <bundle> --out <rumbo>/indice-empresas.json
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bundle = Path(a.bundle).expanduser()
    manifest = json.loads((bundle / "manifest.json").read_text())
    corte = manifest["months"][-1]
    empresas = {}
    for f in sorted((bundle / "companies").glob("*.json")):
        d = json.loads(f.read_text())
        perfil = {x["key"]: x["value"] for x in d["profile"]}
        mes = next((m for m in d["months"] if m["month"] == corte), None)
        empresas[d["id"]] = {
            "group": d["group_id"],
            "size": perfil.get("size_band"),
            "shown": mes["shown"] if mes else None,
            "band": mes["band"] if mes else None,
        }
    salida = {"schema": "rumbo-companies-index-v1", "bundle_id": manifest["bundle_id"], "cut": corte, "companies": empresas}
    Path(a.out).expanduser().write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(empresas)} empresas en el índice (corte {corte}).")


if __name__ == "__main__":
    main()
