# Catálogo de la interfaz previa al rediseño

Documentación exhaustiva del frontend de Embat X-Ray **tal como era antes del rediseño**: qué existe en cada pantalla, qué hace cada elemento, cómo funciona por dentro (estado, URL, datos del bundle, cálculos) y en qué fichero vive.

- **Foto de:** rama `main`, commit `cad5b5a` (19 de septiembre de 2026), con el bundle real `550980d25a18` (250 grupos, 1.286 empresas, 4.402 alertas).
- **No cubre** lo añadido después en `main`: la página `/wiki` y `/wiki/como-puntuamos`.
- **Idioma:** español.

## Cómo leerlo

| Fichero | Uso |
| --- | --- |
| `CATALOGO.html` | Versión navegable con índice lateral y capturas integradas. Ábrela en el navegador o sírvela con `python3 -m http.server -d docs/ui-catalog-pre-redesign 8765`. |
| `CATALOGO.md` | Mismo contenido en Markdown, cómodo para buscar con `rg` o para que lo lea un agente. |
| `capturas/` | 113 capturas reales: escritorio (1440 px), tablet (1024 px) y móvil (390 px). El nombre dice la pantalla y el estado. |

## Contenido

1. **La aplicación:** visión general, arquitectura, rutas, parámetros de URL (`tab`, `focus`, `section`, `m`), estado, cabecera, buscador, barra lateral y selector de mes.
2. **Pantallas:** Radar, Diagnóstico, Escenarios, Acciones, Técnico (desglose, alertas, recibo), página de grupo y página de empresa.
3. **Estados y formatos:** estados vacíos, de error y de carga; adaptación a tablet y móvil.
4. **Piezas:** ficha de cada componente de `src/lib/xray`, primitivas shadcn-svelte, sistema visual y formato es-ES.
5. **Fondo:** contrato del bundle, lógica del score, glosario, accesibilidad, pruebas y observaciones.
6. **Anexo:** ficha de cada una de las 113 capturas.

## Cómo se hizo

Redactado con Gemini a partir del código fuente completo del frontend (fuente de verdad) y de descripciones de las 113 capturas; después se revisó cada sección contra el código y se contrastaron los textos literales entrecomillados con el código y las capturas. Puede quedar alguna imprecisión: ante la duda, manda el código de `cad5b5a`.
