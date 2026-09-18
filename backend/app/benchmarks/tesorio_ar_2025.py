from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TesorioIndustryMetric:
    industry: str
    industry_slug: str
    rank: int
    avg_days_to_collect: float
    open_ar_overdue_ratio: float
    overdue_aging_120d_ratio: float
    ar_health_index: float
    commentary: str


STUDY_ID = "TESORIO_AR_2025"
STUDY_SOURCE = "tesorio"
STUDY_TITLE = "2025 AR Benchmark Report"
STUDY_DATA_PERIOD = "Q4 2024"
STUDY_REPORT_YEAR = 2025
STUDY_SOURCE_URL = "https://www.tesorio.com/documents/tesorio-ar-benchmark-report.pdf"
STUDY_DESCRIPTION = (
    "Industry benchmark for accounts receivable performance across ten sectors, "
    "covering average days to collect, overdue exposure, aging severity, and the "
    "Tesorio AR Health Index."
)

INDUSTRY_METRICS: tuple[TesorioIndustryMetric, ...] = (
    TesorioIndustryMetric(
        industry="Financial Services",
        industry_slug="financial_services",
        rank=1,
        avg_days_to_collect=39,
        open_ar_overdue_ratio=0.11,
        overdue_aging_120d_ratio=0.10,
        ar_health_index=0.84,
        commentary="Top performer: fast, clean, and low risk.",
    ),
    TesorioIndustryMetric(
        industry="Marketing & Advertising",
        industry_slug="marketing_advertising",
        rank=2,
        avg_days_to_collect=39,
        open_ar_overdue_ratio=0.28,
        overdue_aging_120d_ratio=0.03,
        ar_health_index=0.76,
        commentary="Agile and disciplined. Strong cash control.",
    ),
    TesorioIndustryMetric(
        industry="Logistics and Supply Chain",
        industry_slug="logistics_supply_chain",
        rank=3,
        avg_days_to_collect=26,
        open_ar_overdue_ratio=0.24,
        overdue_aging_120d_ratio=0.37,
        ar_health_index=0.67,
        commentary="Very fast to collect, but risk exists.",
    ),
    TesorioIndustryMetric(
        industry="Software",
        industry_slug="software",
        rank=4,
        avg_days_to_collect=48,
        open_ar_overdue_ratio=0.30,
        overdue_aging_120d_ratio=0.23,
        ar_health_index=0.53,
        commentary="Healthy ops, but longer tails.",
    ),
    TesorioIndustryMetric(
        industry="Professional Services",
        industry_slug="professional_services",
        rank=5,
        avg_days_to_collect=50,
        open_ar_overdue_ratio=0.45,
        overdue_aging_120d_ratio=0.26,
        ar_health_index=0.38,
        commentary="Volume-heavy; aging risk is active.",
    ),
    TesorioIndustryMetric(
        industry="Business Services",
        industry_slug="business_services",
        rank=6,
        avg_days_to_collect=65,
        open_ar_overdue_ratio=0.43,
        overdue_aging_120d_ratio=0.23,
        ar_health_index=0.29,
        commentary="Volume-heavy; aging is spread.",
    ),
    TesorioIndustryMetric(
        industry="Healthcare",
        industry_slug="healthcare",
        rank=7,
        avg_days_to_collect=51,
        open_ar_overdue_ratio=0.56,
        overdue_aging_120d_ratio=0.28,
        ar_health_index=0.27,
        commentary="Payer driven friction impacts collections.",
    ),
    TesorioIndustryMetric(
        industry="Manufacturing",
        industry_slug="manufacturing",
        rank=8,
        avg_days_to_collect=60,
        open_ar_overdue_ratio=0.46,
        overdue_aging_120d_ratio=0.37,
        ar_health_index=0.21,
        commentary="Capital intensity + friction = long tail.",
    ),
    TesorioIndustryMetric(
        industry="Technology Services",
        industry_slug="technology_services",
        rank=9,
        avg_days_to_collect=63,
        open_ar_overdue_ratio=0.36,
        overdue_aging_120d_ratio=0.45,
        ar_health_index=0.20,
        commentary="Slower to collect; aging risk is rising.",
    ),
    TesorioIndustryMetric(
        industry="Energy & Utilities",
        industry_slug="energy_utilities",
        rank=10,
        avg_days_to_collect=58,
        open_ar_overdue_ratio=0.50,
        overdue_aging_120d_ratio=0.49,
        ar_health_index=0.12,
        commentary="Worst performer: half overdue, severely aged.",
    ),
)
