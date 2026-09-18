from datetime import date

from .contracts import Driver, ScoreSnapshot


def velasco_snapshot() -> ScoreSnapshot:
    return ScoreSnapshot(
        entity_id="COMP_0680",
        month=date(2026, 9, 1),
        score=68,
        delta=-7,
        trend="deteriorating",
        persistence_months=4,
        confidence=0.92,
        detected_since=date(2026, 5, 1),
        dataset_hash="demo-fixture-2026-09",
        drivers=[
            Driver(feature="collection_delay_days", label="Cobro de clientes", direction="negative", contribution=-7.2, observed=19, baseline=8, evidence="El retraso mediano pasa de 8 a 19 días y persiste durante tres cierres."),
            Driver(feature="credit_line_utilization", label="Uso de líneas", direction="negative", contribution=-4.8, observed=0.81, baseline=0.58, evidence="La utilización supera el 81 % y reduce el margen disponible."),
            Driver(feature="cash_volatility", label="Estabilidad de caja", direction="negative", contribution=-2.5, observed=0.34, baseline=0.18, evidence="La volatilidad aumenta de forma sostenida y no se concentra en un único mes."),
            Driver(feature="supplier_payment_margin", label="Margen de pagos", direction="positive", contribution=0.5, observed=7, baseline=6, evidence="Los pagos a proveedores permanecen dentro de su patrón habitual."),
        ],
    )


def demo_overview() -> dict[str, object]:
    return {
        "group": {"id": "GROUP_0042", "name": "Grupo Velasco", "period": "Septiembre de 2026", "score": 68, "delta": -7},
        "trajectory": [76, 77, 79, 80, 81, 82, 81, 83, 82, 83, 81, 82, 80, 79, 78, 78, 77, 75, 74, 72, 71, 70, 69, 68],
        "companies": [
            {"id": "COMP_0680", "name": "Velasco Industrial", "score": 68, "delta": -14, "signal": "Deterioro persistente", "confidence": "Alta", "intent": "danger"},
            {"id": "COMP_0218", "name": "Northbrook Foods", "score": 65, "delta": 20, "signal": "Mejora estructural", "confidence": "Alta", "intent": "success"},
            {"id": "COMP_0915", "name": "Orbe Retail", "score": 74, "delta": -2, "signal": "Bache puntual", "confidence": "Media", "intent": "warning"},
        ],
        "snapshot": velasco_snapshot().model_dump(mode="json"),
        "actions": [
            {"id": "collect-overdue", "priority": "P1", "title": "Priorizar el cobro de cinco facturas", "rationale": "Explican el 61 % del aumento de días de cobro.", "impact": "+4–6 puntos", "owner": "Tesorería", "status": "En curso", "intent": "danger"},
            {"id": "refinance-line", "priority": "P1", "title": "Renegociar la línea de circulante", "rationale": "La utilización sostenida reduce el colchón disponible.", "impact": "+180 k€ de margen", "owner": "CFO", "status": "Por iniciar", "intent": "warning"},
            {"id": "monitor-volatility", "priority": "P2", "title": "Vigilar la volatilidad de caja", "rationale": "La señal aislada todavía no justifica una intervención.", "impact": "Revisar en el próximo cierre", "owner": "Analista", "status": "Monitorizando", "intent": "neutral"},
        ],
    }
