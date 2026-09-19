"""Copia verificada de los parámetros del motor para Rumbo.

Lee params/reference_v1.json del repositorio del motor y comprueba que su huella (campo sha256)
es la misma que la del bundle servido (manifest.params_hash). Si no coincide, no escribe nada:
la sección técnica nunca dibuja curvas de otros parámetros distintos de los que puntuaron.
Solo stdlib.

Uso: python3 scripts/datos/parametros.py --params <motor>/params/reference_v1.json --bundle <bundle> --out <rumbo>/params.json
"""

import argparse
import json
import sys
from pathlib import Path

CLAVES = ["anchors", "liquidity", "penalty", "caps", "bands", "weights", "reference", "trajectory",
          "confidence", "size_bands", "alerts", "invoices", "activity", "debt", "abstention", "profile"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    params = json.loads(Path(a.params).read_text())
    manifest = json.loads((Path(a.bundle) / "manifest.json").read_text())
    if params.get("sha256") != manifest.get("params_hash"):
        print(f"La huella de los parámetros ({params.get('sha256', '')[:12]}) no es la del bundle "
              f"({manifest.get('params_hash', '')[:12]}): no se escribe nada.", file=sys.stderr)
        return 1
    salida = {"schema": "rumbo-params-v1", "sha256": params["sha256"], "version": params.get("version"),
              "verified_against_manifest": True, "bundle_id": manifest["bundle_id"]}
    for clave in CLAVES:
        if clave in params:
            salida[clave] = params[clave]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    print(f"Parámetros {params['sha256'][:12]} verificados contra el bundle {manifest['bundle_id'][:12]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
