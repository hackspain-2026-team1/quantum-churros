#!/usr/bin/env bash
# Prepara todo lo que lee Rumbo a partir de los datos del reto y del motor. Nada se escribe a mano.
#   1. Bundle del motor (xray-export-v1) con validación, desde el repositorio del motor.
#   2. params.json: copia de los parámetros verificada contra el bundle.
#   3. products/: productos contratados por empresa y grupo.
#   4. horizons/: el futuro, simulado y puntuado con el motor, con su prueba hacia atrás.
#   5. Enlaces public/datos y public/rumbo.
# Uso: scripts/datos/preparar.sh [carpeta_datos] [repositorio_motor]
set -euo pipefail
DATOS="${1:-$HOME/Developer/hackspain-data}"
MOTOR="${2:-$HOME/Developer/hackspain-motor}"
AQUI="$(cd "$(dirname "$0")/../.." && pwd)"
BUNDLE="$DATOS/bundle-main"; ART="$DATOS/artifacts-main"; RUMBO="$DATOS/rumbo"
mkdir -p "$ART" "$RUMBO"
echo "1/5 · motor: validación y exportación"
( cd "$MOTOR" && uv run --package xray-engine xray-score validate "$DATOS/raw" --out "$ART/validation.json" || echo "   (la validación marca alguna comprobación como no superada; el recibo lo enseña)" )
( cd "$MOTOR" && uv run --package xray-engine xray-score predict "$DATOS/raw" --out "$ART" --export-dir "$BUNDLE" --evidence-months 24 )
echo "2/5 · parámetros verificados"
python3 "$AQUI/scripts/datos/parametros.py" --params "$MOTOR/params/reference_v1.json" --bundle "$BUNDLE" --out "$RUMBO/params.json"
python3 "$AQUI/scripts/datos/indice.py" --bundle "$BUNDLE" --out "$RUMBO/indice-empresas.json"
echo "3/5 · productos contratados"
uv run --no-project --with polars --with pyarrow python "$AQUI/scripts/datos/productos.py" --parquet "$DATOS/parquet" --raw "$DATOS/raw" --params "$MOTOR/params/reference_v1.json" --out "$RUMBO/products" --cut 2026-08
echo "4/5 · horizontes"
( cd "$MOTOR" && uv run --package xray-engine python "$AQUI/scripts/datos/horizontes.py" --panel "$ART/panel.parquet" --bundle "$BUNDLE" --params "$MOTOR/params/reference_v1.json" --out "$RUMBO/horizons" --cut 2026-08 --sims 400 --seed 7 )
echo "5/5 · enlaces"
ln -sfn "$BUNDLE" "$AQUI/public/datos"
ln -sfn "$RUMBO" "$AQUI/public/rumbo"
echo "Listo. Si el servidor de desarrollo ya estaba arrancado, reinícialo (Vite no ve los enlaces nuevos)."
