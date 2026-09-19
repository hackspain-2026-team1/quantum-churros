"""Etiquetas legibles para informes de evaluación (sin acrónimos internos).

Convención (ver docs/engine/EVALUATION.md § Estilo de presentación):
- Informes para personas: nombre en castellano + «qué se prueba» + resultado.
- Códigos P1/R6/holdout solo en VALIDATION.md y validation.json.
"""

from __future__ import annotations

CHECK_LABELS: dict[str, str] = {
    "isolation": "Aislamiento de cohorte (60 grupos puntuados en solitario)",
    "truncation": "Sin mirar al futuro (cortar el histórico no cambia el pasado)",
    "additivity": "Identidad aditiva (el desglose cuadra con el score)",
    "scale": "Invarianza de escala (multiplicar importes no cambia el score)",
    "determinism": "Determinismo (misma entrada, misma salida)",
    "ablation": "Ablación pareada (conectar ERP no mueve el score solo)",
    "neutrality": "Neutralidad (el score no es proxy de tamaño, ERP o banco)",
    "rank_stability": "Estabilidad del orden (los pesos no deciden el ranking)",
    "netting_placebo": "Placebo de traspasos (espejos y reversiones reales, no azar)",
    "rolling_origin": "Origen rodante (re-puntuar en cortes históricos)",
    "injection": "Deterioros inyectados (pico, escalón, rampa)",
    "natural_anticipation": "Anticipación natural (AUC y meses de antelación)",
    "level_vs_slope": "Nivel frente a pendiente",
    "persistence": "Persistencia de nivel (el score bajo sigue bajo)",
    "verdict_persistence": "Persistencia de veredictos (estructural vs bache)",
}

KPI_HISTORY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fecha", "Fecha del run"),
    ("dataset", "Huella del dataset"),
    ("params", "Huella de parámetros"),
    ("motor", "Versión del motor"),
    (
        "traspasos_ok",
        "Traspasos internos: los espejos reales superan al placebo de fechas",
    ),
    (
        "sin_futuro_ok",
        "Sin mirar al futuro: cortar datos en un mes pasado no altera ese mes",
    ),
    (
        "escala_ok",
        "Invarianza de escala: ×1024 en importes no mueve el score",
    ),
    ("pct_puntuables", "Grupos puntuables en el último mes (%)"),
    ("grupos_ensayo", "Grupos en el ensayo aislado (proxy del test oculto)"),
    (
        "persistencia_nivel",
        "Persistencia de nivel: correlación del score a 3 meses de distancia",
    ),
    (
        "persistencia_pendiente",
        "Persistencia de pendiente: correlación del cambio mensual a 3 meses",
    ),
    (
        "origen_rodante",
        "Origen rodante: correlación mínima al re-puntuar en cortes 2025-11, 2026-02, 2026-05",
    ),
    (
        "pico_vs_caida",
        "Probabilidad de llamar «caída estructural» a un pico de un mes",
    ),
    ("runtime", "Duración del run (segundos)"),
)

BAND_LABELS: dict[str, str] = {
    "critical": "Crítico",
    "watch": "Vigilancia",
    "stable": "Estable",
    "solid": "Sólido",
}
