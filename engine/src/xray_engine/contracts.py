from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Driver(BaseModel):
    feature: str
    label: str
    direction: Literal["positive", "negative", "neutral"]
    contribution: float
    observed: float
    baseline: float
    evidence: str
    source: Literal["observable", "predictive"] = "predictive"


class ScoreSnapshot(BaseModel):
    entity_id: str
    month: date
    score: float = Field(ge=0, le=100)
    observed_score: float = Field(ge=0, le=100)
    predicted_future_score: float = Field(ge=0, le=100)
    forecast_delta: float
    delta: float
    trend: Literal["improving", "stable", "deteriorating"]
    persistence_months: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    drivers: list[Driver]
    shap_base_value: float
    explanation_residual: float
    detected_since: date | None
    feature_version: str = "features-v2"
    model_version: str = "catboost-v1"
    dataset_hash: str
