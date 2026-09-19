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
| `public/rumbo/` | `params.json`, `entities.json`, `products/`, `horizons/` | `scripts/datos/` |

`scripts/datos/preparar.sh [carpeta_datos] [repositorio_motor]` hace los cinco pasos y crea los enlaces. Nada se escribe a mano: si falta un fichero de `rumbo/`, la interfaz lo dice y no lo rellena.

`entities.json` contiene el índice agregado y los nombres ficticios de grupos y empresas. `scripts/datos/entidades.py` lo deriva de forma determinista a partir de los identificadores y metadatos del bundle; el score no participa en los nombres. En el repositorio completo, `make db-sync` regenera el bundle y este índice en una sola operación.

Con `?datos=sinteticos`, y solo en desarrollo, se usa una cartera sintética con la forma exacta del contrato. El build de producción no la incluye.

## El monitor y «dile qué quieres ver»

La portada es el monitor de la cartera: `src/vistas/monitor.ts`, con la lógica en `src/datos/monitorCartera.ts` y las formas de arena en `src/arena/vistas.ts`. `src/datos/monitor.ts` es otra cosa: el ciclo de la señal de una entidad.

El campo «o dile qué quieres ver» entiende la frase en dos capas:
- palabras clave, en el navegador;
- Jev, a través del Worker `worker/` (`rumbo-vista`). Su dirección está en `.env.production` y `.env.development` (`VITE_VISTA_URL`) y es pública; la clave de TypeSafe es un secreto del Worker.

Para desplegar el Worker, desde `worker/`:

```sh
bunx wrangler@4 deploy
bunx wrangler@4 secret put TYPESAFE_API_KEY
```

La clave se escribe en el aviso de wrangler, nunca en la línea de órdenes.

`bun pruebas/jev/evaluar.mjs` mide cuánto acierta, con el servidor de desarrollo arrancado. Sin `VITE_VISTA_URL`, el monitor entiende solo por palabras clave.

## Despliegue

Rumbo es la única aplicación de la imagen `web` y se sirve desde **`/`** mediante el servidor estático del contenedor. No hace falta otro contenedor ni otro puerto.

- `docker/frontend.Dockerfile` ejecuta `bun run check && bun run build:despliegue` y copia `dist/` a la imagen final.
- `build:despliegue` construye con base `/` y con las raíces de datos de producción, y después pasa `scripts/comprobar-build.mjs`. Ese guardián falla si el build lleva datos, la cartera sintética, identificadores escritos a mano, peticiones a terceros o recursos fuera de la base.
- En producción los datos no van en la imagen. Rumbo lee:
  - el bundle, en `/data/v1/`, montado en `/usr/share/nginx/html/data/v1` desde `/opt/quantum-churros/bundle`;
  - sus datos derivados, en `/data/rumbo/`, montados en `/usr/share/nginx/html/data/rumbo` desde `/opt/quantum-churros/rumbo` (`deploy/compose.yaml`).

  Los datos de Rumbo van en una carpeta hermana y no dentro del bundle. Así no se toca la huella del bundle (`bundle_id` es el sha256 de todos sus ficheros) ni su prueba de integridad, que recorre todos sus JSON.

### Puesta en marcha en `datons-dev` (una vez, con permisos de administración)

La cuenta `quantum-deploy` no puede escribir en `/opt/quantum-churros`. Estos pasos los hace quien administra el servidor:

1. Sustituir los montajes del servicio `web` de `/opt/quantum-churros/compose.yaml` por los destinos de la imagen Vite, igual que en `deploy/compose.yaml`:
   ```yaml
   - ./bundle:/usr/share/nginx/html/data/v1:ro
   - ./rumbo:/usr/share/nginx/html/data/rumbo:ro
   ```
2. Copiar los datos generados con `bun run datos`, **del mismo bundle que está desplegado**, en `/opt/quantum-churros/rumbo/` (propiedad de root, solo lectura para el contenedor).
3. Recrear `web` para aplicar el montaje. El siguiente despliegue también lo hace.

El paso 1 debe aplicarse junto con el primer despliegue de esta imagen: la imagen Svelte anterior montaba el bundle bajo `/app/build/client`, una ruta que ya no existe. Mientras falte únicamente el paso 2, `/` funciona con el bundle y avisa de que faltan los productos y los horizontes.

Cada fichero de `rumbo/` lleva el `bundle_id` del que sale. Si alguien vuelve a exportar el bundle sin regenerar `rumbo/`, la sección Técnico lo señala («distinto del que se ve»).

### Comprobarlo en local contra el servidor de producción

```sh
bun run build:despliegue
mkdir -p dist/data
ln -sfn <bundle> dist/data/v1
ln -sfn <rumbo> dist/data/rumbo
busybox httpd -f -p 3999 -h dist
XRAY_URL=http://127.0.0.1:3999/ XRAY_DATOS=/data/v1/ XRAY_RUMBO=/data/rumbo/ bun pruebas/recorrido.mjs
```
