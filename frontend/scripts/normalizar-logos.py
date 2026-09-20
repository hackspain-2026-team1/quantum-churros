"""Normaliza los logotipos de `src/vistas/logos.ts` para que todas las marcas se vean iguales.

Los favicons de los que salen traen cada uno su propio margen: el de Abanca ocupa el 58 % de su
lienzo y se sienta bajo, el de BBVA lo llena entero. Puestos en fila, las marcas no se alinean ni
tienen el mismo tamaño. Aquí se recorta cada logo a su tinta y se vuelve a centrar en un lienzo
cuadrado, de modo que la caja y el dibujo coincidan siempre.

  uv run --with pillow scripts/normalizar-logos.py [--escribir]

Sin `--escribir` solo informa. Los logotipos son de sus titulares; esto no los altera, solo quita
el margen del favicon. Las marcas en SVG (Simple Icons) ya vienen normalizadas y no se tocan.
"""
import argparse
import base64
import io
import re
import sys
from collections import deque
from pathlib import Path

from PIL import Image

FUENTE = Path(__file__).resolve().parent.parent / "src" / "vistas" / "logos.ts"
BLANCO = 24  # Cuánto puede alejarse del blanco un píxel y seguir siendo margen del favicon.


def sin_margen_blanco(im: Image.Image) -> Image.Image:
    """Quita el fondo blanco del favicon, pero solo el que rodea al dibujo desde el borde.

    Un umbral a secas agujerearía los blancos interiores (la llama de Santander, el chevrón de
    BBVA); por eso se inunda desde los bordes y se para en cuanto encuentra tinta.
    """
    ancho, alto = im.size
    px = im.load()
    fuera, cola = set(), deque()
    for x in range(ancho):
        cola.extend([(x, 0), (x, alto - 1)])
    for y in range(alto):
        cola.extend([(0, y), (ancho - 1, y)])
    while cola:
        x, y = cola.popleft()
        if (x, y) in fuera or not (0 <= x < ancho and 0 <= y < alto):
            continue
        r, g, b, a = px[x, y]
        if a != 0 and min(r, g, b) < 255 - BLANCO:
            continue
        fuera.add((x, y))
        cola.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    for x, y in fuera:
        px[x, y] = (255, 255, 255, 0)
    return im


def normalizar(datos: bytes) -> tuple[bytes, str]:
    """Recorta el margen y centra la tinta en un cuadrado. No se reescala: un favicon de 16 px
    ampliado solo sería un favicon de 16 px borroso; quien decide el tamaño es el CSS."""
    im = Image.open(io.BytesIO(datos)).convert("RGBA")
    antes = im.size
    im = sin_margen_blanco(im)
    caja = im.getchannel("A").getbbox()
    if caja is None:
        raise ValueError("el logotipo se ha quedado sin tinta")
    tinta = im.crop(caja)
    lado = max(tinta.size)
    lienzo = Image.new("RGBA", (lado, lado), (255, 255, 255, 0))
    lienzo.paste(tinta, ((lado - tinta.width) // 2, (lado - tinta.height) // 2))
    salida = io.BytesIO()
    lienzo.save(salida, "PNG", optimize=True)
    return salida.getvalue(), f"{antes[0]}×{antes[1]} → tinta {tinta.width}×{tinta.height} en {lado}×{lado}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--escribir", action="store_true", help="reescribe logos.ts en el sitio")
    args = parser.parse_args()
    texto = FUENTE.read_text()
    cambios = 0

    def reemplazo(m: re.Match[str]) -> str:
        nonlocal cambios
        clave, cabecera, carga = m.group(1), m.group(2), m.group(3)
        if "svg" in cabecera:
            print(f"{clave:16s} SVG, ya normalizado")
            return m.group(0)
        antes = base64.b64decode(carga)
        despues, detalle = normalizar(antes)
        cambios += 1
        print(f"{clave:16s} {detalle:34s} {len(antes) / 1024:5.1f} kB → {len(despues) / 1024:5.1f} kB")
        return f"\t{clave}: 'data:image/png;base64,{base64.b64encode(despues).decode()}'"

    nuevo = re.sub(r"\t([a-z0-9]+): '(data:image/[a-z+]+;base64),([^']+)'", reemplazo, texto)
    if args.escribir:
        FUENTE.write_text(nuevo)
        print(f"\n{cambios} logotipos normalizados en {FUENTE.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
