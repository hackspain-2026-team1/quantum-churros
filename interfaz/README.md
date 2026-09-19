# Rumbo

Interfaz de Rumbo para el reto X Ray de Embat: organización → empresa → cuatro secciones (Scoring, Productos, Acciones, Técnico), con la cartera dibujada en arena (WebGL2). Es TypeScript sin framework, construido con Vite y Bun. El diario de diseño y de decisiones está en [`DIARIO.md`](DIARIO.md).

## Desarrollo

```sh
bun install
bun run datos      # genera los datos (necesita el dataset y el motor; ver abajo)
bun run dev        # http://127.0.0.1:5317/
bun run prueba     # recorrido de 36 comprobaciones con Chrome sobre los datos reales
```

En desarrollo, Rumbo lee dos carpetas enlazadas en `public/` (fuera de git):

| Carpeta | Contenido | Origen |
| --- | --- | --- |
| `public/datos/` | bundle del motor (`xray-export-v1`) | `xray-score predict --export-dir` |
| `public/rumbo/` | `params.json`, `indice-empresas.json`, `products/`, `horizons/` | `scripts/datos/` |

`scripts/datos/preparar.sh [carpeta_datos] [repositorio_motor]` hace los cinco pasos y crea los enlaces. Nada se escribe a mano: si falta un fichero de `rumbo/`, la interfaz lo dice y no lo rellena.

Con `?datos=sinteticos`, y solo en desarrollo, se usa una cartera sintética con la forma exacta del contrato. El build de producción no la incluye.

## Despliegue

Rumbo viaja dentro de la imagen `web` y se sirve en **`/rumbo/`**, con el mismo servidor que la aplicación SvelteKit. No hace falta ni un contenedor ni un puerto nuevos.

- `docker/frontend.Dockerfile` tiene una etapa `rumbo` que ejecuta `bun run check && bun run build:despliegue` y copia `dist/` a `build/client/rumbo/`.
- `build:despliegue` construye con base `/rumbo/` y con las raíces de datos de producción, y después pasa `scripts/comprobar-build.mjs`. Ese guardián falla si el build lleva datos, la cartera sintética, identificadores escritos a mano, peticiones a terceros o recursos fuera de la base.
- En producción los datos no van en la imagen. Rumbo lee:
  - el bundle, en `/data/v1/`, que es el mismo montaje que ya usa la aplicación (`/opt/quantum-churros/bundle`);
  - sus datos derivados, en `/data/rumbo/`, montados desde `/opt/quantum-churros/rumbo` (`deploy/compose.yaml`).

  Los datos de Rumbo van en una carpeta hermana y no dentro del bundle. Así no se toca la huella del bundle (`bundle_id` es el sha256 de todos sus ficheros) ni su prueba de integridad, que recorre todos sus JSON.

### Puesta en marcha en `datons-dev` (una vez, con permisos de administración)

La cuenta `quantum-deploy` no puede escribir en `/opt/quantum-churros`. Estos pasos los hace quien administra el servidor:

1. Añadir al servicio `web` de `/opt/quantum-churros/compose.yaml` el montaje nuevo, igual que en `deploy/compose.yaml`:
   ```yaml
   - ./rumbo:/app/build/client/data/rumbo:ro
   ```
2. Copiar los datos generados con `bun run datos`, **del mismo bundle que está desplegado**, en `/opt/quantum-churros/rumbo/` (propiedad de root, solo lectura para el contenedor).
3. Reiniciar `web` para que el servidor estático vea los ficheros (los indexa al arrancar). El siguiente despliegue también lo hace.

Mientras falten los pasos 1 y 2, `/rumbo/` funciona igualmente con el bundle y avisa de que faltan los productos y los horizontes.

Cada fichero de `rumbo/` lleva el `bundle_id` del que sale. Si alguien vuelve a exportar el bundle sin regenerar `rumbo/`, la sección Técnico lo señala («distinto del que se ve»).

### Comprobarlo en local contra el servidor de producción

```sh
bun run build:despliegue
cd ../frontend && bun run build
cp -R ../interfaz/dist build/client/rumbo
mkdir -p build/client/data
cp -RL <bundle> build/client/data/v1
cp -RL <rumbo> build/client/data/rumbo
PORT=3999 bun build/index.js
XRAY_URL=http://127.0.0.1:3999/rumbo/ XRAY_DATOS=/data/v1/ XRAY_RUMBO=/data/rumbo/ bun ../interfaz/pruebas/recorrido.mjs
```
