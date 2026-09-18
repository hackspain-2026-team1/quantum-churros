from __future__ import annotations

from pathlib import Path

import polars as pl

from .features import FEATURE_VERSION, build_monthly_features
from .modeling import MODEL_VERSION, dataset_hash, score_with_model


def score_dataset(input_dir: Path, model_dir: Path) -> pl.DataFrame:
    features = build_monthly_features(input_dir, include_targets=False)
    return score_with_model(features, model_dir, dataset_hash(input_dir))


__all__ = [
    "FEATURE_VERSION",
    "MODEL_VERSION",
    "build_monthly_features",
    "score_dataset",
    "score_with_model",
]
