from xray_engine.industry_classifier import INDUSTRY_LABELS

DEMO_INDUSTRY_OVERRIDES: dict[str, tuple[str, str]] = {
    "COMP_0680": ("manufacturing", "Override demo: Velasco Industrial"),
    "COMP_0218": ("logistics_supply_chain", "Override demo: Northbrook Foods"),
    "COMP_0915": ("marketing_advertising", "Override demo: Orbe Retail"),
}


def apply_demo_override(entity_id: str, classification: dict[str, object]) -> dict[str, object]:
    override = DEMO_INDUSTRY_OVERRIDES.get(entity_id.upper())
    if override is None:
        return classification
    slug, reason = override
    return {
        **classification,
        "industry_slug": slug,
        "industry_label": INDUSTRY_LABELS[slug],
        "confidence": 1.0,
        "source": "override",
        "reason": reason,
    }
