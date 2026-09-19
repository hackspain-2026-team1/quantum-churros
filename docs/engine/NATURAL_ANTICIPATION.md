# Anticipación y retardo de detección

El motor separa dos preguntas que no deben mezclarse:

1. **Cartera observada:** si la trayectoria publicada hoy ordena los futuros onsets estructurales internos del propio motor.
2. **Inyección con onset conocido:** cuánto discrimina y cuánto tarda en reaccionar ante un escalón o una rampa introducidos de forma controlada.

No hay etiquetas de impago. La AUC de cartera mide consistencia temporal frente a futuros veredictos o alertas estructurales, no probabilidad de quiebra. Una inyección exógena tampoco puede anticiparse antes de su onset: ahí se publican discriminación y retardo desde el cambio.

## Definiciones

| Término | Definición |
|---|---|
| Onset natural | Primer mes de un episodio estructural que no estaba activo el mes anterior |
| Señal previa | Veredicto de deterioro o caída relevante del score en los seis meses anteriores al onset |
| Anticipación interna | Meses entre la primera señal previa y el onset natural |
| Onset inyectado | Primer mes en el que se modifica el rastro financiero |
| Primera detección | Primer veredicto de deterioro adicional frente a la serie intacta |
| Confirmación estructural | Primer veredicto estructural adicional frente a la serie intacta |
| AUC pareada | Capacidad del score para separar cada trayectoria inyectada de su misma trayectoria intacta durante los primeros h meses |

Cada horizonte utiliza todo el seguimiento que le corresponde. El horizonte de tres meses no se recorta por exigir doce meses futuros.

## Baseline de CI

Dataset sintético determinista de `engine/tests/conftest.py`, seis grupos, semilla 7. Estas cifras calibran el harness; no son resultados de la cartera del reto ni deben usarse como titular comercial.

| Forma | AUC pareada h=6 | Primera detección mediana | Confirmación estructural mediana | Cobertura estructural |
|---|---:|---:|---:|---:|
| Escalón | 0,944 | 1 mes | 2 meses | 100 % |
| Rampa | 0,813 | 4 meses | 5,5 meses | 100 % |

Gates de CI:

- AUC h=6 de escalón ≥ 0,80.
- AUC h=6 de rampa ≥ 0,70.
- El escalón se detecta antes que la rampa.
- Confirmación estructural mediana del escalón ≤ 3 meses.
- AUC con scores empatados = 0,50.

## Publicación de la cartera observada

Ejecutar:

```bash
make validate XRAY_DATA=data/raw
make eval-anticipation
```

Una AUC de cartera solo se enseña si el horizonte tiene ambas clases y un número de onsets suficiente para no convertir uno o dos casos en titular. Siempre se publica junto a `n_pos`, `n_neg`, número de grupos, distribución de anticipación y hashes de dataset y parámetros. Si no hay positivos, el resultado correcto es «no estimable», nunca cero ni cien por cien.

## Métricas killer

### Para mejorar el motor

1. **Confirmación estructural del escalón:** mediana y p75 desde onset. Objetivo de demo: mediana ≤ 3 meses.
2. **Rampa no detectada a nueve meses:** principal debilidad conocida; debe bajar sin elevar falsos estructurales en picos.
3. **P(estructural | pico):** guardrail de estabilidad. Objetivo ≤ 10 %.
4. **Cobertura estructural step/ramp:** evita mejorar la mediana ignorando los casos que nunca se detectan.
5. **Falsas alertas en cartera tranquila:** coste operativo del monitor por 100 grupo-años.
6. **AUC pareada por forma y tamaño:** detecta bandas en las que el score apenas reacciona.
7. **Anticipación natural h=3/h=6 con soporte:** útil solo con suficientes onsets y siempre descrita como outcome interno.

### Para la demo

El jurado debe recordar tres cifras, no una tabla completa:

- **Bache:** porcentaje de picos confundidos con caída estructural.
- **Cambio real:** meses hasta detectar y confirmar un escalón.
- **Deriva lenta:** cobertura y retardo de la rampa, presentada como límite honesto.

AUC es evidencia técnica de respaldo. No debe abrir la demo ni sustituir una historia de empresa, alerta, causa y acción.

## Riesgos de interpretación

- La AUC natural comparte sistema de definición con el score; no es un outcome externo.
- Comparar solo medianas oculta los casos no detectados; publicar también cobertura y p75.
- Un AUC alto en inyección puede coexistir con confirmación lenta; discriminación y tiempo responden preguntas distintas.
- Optimizar el retardo sin vigilar picos y falsas alertas convierte el monitor en ruido.
