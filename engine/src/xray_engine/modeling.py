from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor, Pool
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from .features import (
    CATEGORICAL_FEATURES,
    FEATURE_VERSION,
    FORECAST_HORIZON_MONTHS,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
)

MODEL_VERSION = "catboost-v1"
OBSERVED_WEIGHT = 0.55
PREDICTED_WEIGHT = 0.45

FEATURE_LABELS = {
    "cash_margin": "Margen de caja",
    "cash_margin_3m": "Margen de caja a tres meses",
    "cash_margin_6m": "Margen de caja a seis meses",
    "cash_margin_change_3m": "Cambio del margen de caja",
    "net_flow_3m": "Flujo neto a tres meses",
    "net_flow_6m": "Flujo neto a seis meses",
    "net_flow_volatility_6m": "Volatilidad del flujo de caja",
    "inflow_3m": "Entradas medias",
    "outflow_3m": "Salidas medias",
    "inflow_change_3m": "Cambio de entradas",
    "collection_delay_days": "Retraso de cobro",
    "collection_delay_3m": "Retraso de cobro persistente",
    "collection_delay_change_3m": "Cambio del retraso de cobro",
    "receivable_open_ratio": "Cuentas por cobrar abiertas",
    "receivable_overdue_ratio": "Cuentas por cobrar vencidas",
    "payable_overdue_ratio": "Cuentas por pagar vencidas",
    "overdue_change_3m": "Cambio de vencidos",
    "reconciled_rate": "Calidad de conciliación",
    "counterparty_count": "Contrapartes activas",
    "counterparty_count_3m": "Diversificación persistente",
    "transaction_count": "Actividad bancaria",
    "invoice_count": "Actividad de facturación",
    "months_observed": "Historial disponible",
}


def dataset_hash(input_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("companies.csv", "transactions.csv", "invoices.csv"):
        path = input_dir / name
        digest.update(name.encode())
        digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:16]


def group_temporal_split(
    frame: pl.DataFrame,
    validation_months: int = 3,
    validation_group_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    labelled = frame.filter(pl.col("future_health").is_not_null())
    months = sorted(labelled["month"].unique().to_list())
    if len(months) <= validation_months:
        raise ValueError("Not enough labelled months for a temporal validation window")
    cutoff = months[-validation_months]
    groups = sorted(labelled["group_id"].unique().to_list())
    if len(groups) < 2:
        raise ValueError(
            "At least two business groups are required for grouped validation"
        )
    random = np.random.default_rng(seed)
    random.shuffle(groups)
    validation_count = min(
        len(groups) - 1, max(1, round(len(groups) * validation_group_fraction))
    )
    validation_groups = set(groups[:validation_count])
    train = labelled.filter(
        (~pl.col("group_id").is_in(validation_groups)) & (pl.col("month") < cutoff)
    )
    validation = labelled.filter(
        pl.col("group_id").is_in(validation_groups) & (pl.col("month") >= cutoff)
    )
    if train.is_empty() or validation.is_empty():
        raise ValueError("The grouped temporal split produced an empty partition")
    details = {
        "cutoff_month": cutoff.isoformat(),
        "training_rows": train.height,
        "validation_rows": validation.height,
        "training_groups": train["group_id"].n_unique(),
        "validation_groups": validation["group_id"].n_unique(),
    }
    return train, validation, details


def _model_frame(frame: pl.DataFrame) -> pd.DataFrame:
    result = frame.select(MODEL_FEATURES).to_pandas()
    for column in CATEGORICAL_FEATURES:
        result[column] = result[column].fillna("UNKNOWN").astype(str)
    for column in NUMERIC_FEATURES:
        result[column] = result[column].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return result


def _direction(values: np.ndarray, threshold: float = 3.0) -> np.ndarray:
    return np.where(
        values >= threshold,
        "improving",
        np.where(values <= -threshold, "deteriorating", "stable"),
    )


def _metrics(
    validation: pl.DataFrame, predictions: np.ndarray
) -> dict[str, float | int]:
    actual = validation["future_health"].to_numpy()
    observed = validation["observed_health"].to_numpy()
    actual_direction = _direction(actual - observed)
    predicted_direction = _direction(predictions - observed)
    changing = actual_direction != "stable"
    correct_change = changing & (actual_direction == predicted_direction)
    correlation = spearmanr(actual, predictions).statistic
    return {
        "rmse": round(float(root_mean_squared_error(actual, predictions)), 4),
        "mae": round(float(mean_absolute_error(actual, predictions)), 4),
        "spearman": round(float(correlation if not np.isnan(correlation) else 0.0), 4),
        "directional_accuracy": round(
            float(np.mean(actual_direction == predicted_direction)), 4
        ),
        "improving_recall": round(
            float(
                np.mean(
                    predicted_direction[actual_direction == "improving"] == "improving"
                )
            )
            if np.any(actual_direction == "improving")
            else 0.0,
            4,
        ),
        "deteriorating_recall": round(
            float(
                np.mean(
                    predicted_direction[actual_direction == "deteriorating"]
                    == "deteriorating"
                )
            )
            if np.any(actual_direction == "deteriorating")
            else 0.0,
            4,
        ),
        "stable_recall": round(
            float(
                np.mean(predicted_direction[actual_direction == "stable"] == "stable")
            )
            if np.any(actual_direction == "stable")
            else 0.0,
            4,
        ),
        "effective_lead_time_months": round(
            float(FORECAST_HORIZON_MONTHS * np.mean(correct_change[changing]))
            if np.any(changing)
            else 0.0,
            4,
        ),
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
    }


def _fit(
    frame: pl.DataFrame,
    iterations: int,
    seed: int,
    evaluation: pl.DataFrame | None = None,
) -> CatBoostRegressor:
    training_pool = Pool(
        _model_frame(frame),
        label=frame["future_health"].to_numpy(),
        cat_features=CATEGORICAL_FEATURES,
    )
    evaluation_pool = None
    if evaluation is not None:
        evaluation_pool = Pool(
            _model_frame(evaluation),
            label=evaluation["future_health"].to_numpy(),
            cat_features=CATEGORICAL_FEATURES,
        )
    model = CatBoostRegressor(
        loss_function="RMSE",
        eval_metric="RMSE",
        iterations=iterations,
        depth=6,
        learning_rate=0.04,
        l2_leaf_reg=5.0,
        random_seed=seed,
        allow_writing_files=False,
        verbose=False,
    )
    model.fit(
        training_pool,
        eval_set=evaluation_pool,
        early_stopping_rounds=50 if evaluation_pool is not None else None,
    )
    return model


def train_model(
    features: pl.DataFrame,
    model_dir: Path,
    source_hash: str,
    iterations: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    train, validation, split = group_temporal_split(features, seed=seed)
    validation_model = _fit(
        train, iterations=iterations, seed=seed, evaluation=validation
    )
    validation_pool = Pool(_model_frame(validation), cat_features=CATEGORICAL_FEATURES)
    predictions = validation_model.predict(validation_pool)
    metrics = _metrics(validation, predictions)
    shap_values = validation_model.get_feature_importance(
        validation_pool, type="ShapValues"
    )
    shap_summary = sorted(
        (
            {"feature": feature, "mean_absolute_shap": round(float(value), 6)}
            for feature, value in zip(
                MODEL_FEATURES, np.abs(shap_values[:, :-1]).mean(axis=0), strict=True
            )
        ),
        key=lambda item: item["mean_absolute_shap"],
        reverse=True,
    )
    labelled = features.filter(pl.col("future_health").is_not_null())
    final_model = _fit(
        labelled, iterations=max(50, validation_model.tree_count_), seed=seed
    )
    medians = {column: float(labelled[column].median()) for column in NUMERIC_FEATURES}
    metadata = {
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "dataset_hash": source_hash,
        "forecast_horizon_months": FORECAST_HORIZON_MONTHS,
        "observed_weight": OBSERVED_WEIGHT,
        "predicted_weight": PREDICTED_WEIGHT,
        "model_features": MODEL_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_feature_medians": medians,
        "validation": split,
        "metrics": metrics,
        "shap_summary": shap_summary,
        "trees": final_model.tree_count_,
        "seed": seed,
    }
    model_dir.mkdir(parents=True, exist_ok=True)
    final_model.save_model(model_dir / "model.cbm")
    (model_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    )
    (model_dir / "metrics.json").write_text(
        json.dumps({"split": split, "metrics": metrics}, indent=2, ensure_ascii=False)
        + "\n"
    )
    return metadata


def load_model(model_dir: Path) -> tuple[CatBoostRegressor, dict[str, Any]]:
    metadata = json.loads((model_dir / "metadata.json").read_text())
    if metadata["feature_version"] != FEATURE_VERSION:
        raise ValueError(
            f"Model expects {metadata['feature_version']}, but the engine provides {FEATURE_VERSION}"
        )
    model = CatBoostRegressor()
    model.load_model(model_dir / "model.cbm")
    return model, metadata


def _drivers(
    row: dict[str, Any], shap_row: np.ndarray, medians: dict[str, float]
) -> tuple[list[dict[str, Any]], float]:
    numeric_items = []
    categorical_total = 0.0
    for feature, value in zip(MODEL_FEATURES, shap_row[:-1], strict=True):
        contribution = float(value) * PREDICTED_WEIGHT
        if feature in CATEGORICAL_FEATURES:
            categorical_total += contribution
            continue
        observed = float(row[feature])
        baseline = float(medians[feature])
        numeric_items.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature.replace("_", " ").title()),
                "direction": "positive"
                if contribution > 0
                else "negative"
                if contribution < 0
                else "neutral",
                "contribution": round(contribution, 4),
                "observed": round(observed, 4),
                "baseline": round(baseline, 4),
                "evidence": f"Valor observado {observed:.2f} frente a una referencia de {baseline:.2f}.",
                "source": "predictive",
            }
        )
    numeric_items.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    selected = numeric_items[:6]
    omitted = categorical_total + sum(
        item["contribution"] for item in numeric_items[6:]
    )
    return selected, omitted


def score_with_model(
    features: pl.DataFrame, model_dir: Path, source_hash: str
) -> pl.DataFrame:
    model, metadata = load_model(model_dir)
    pool = Pool(_model_frame(features), cat_features=CATEGORICAL_FEATURES)
    predictions = np.asarray(model.predict(pool), dtype=float).clip(0, 100)
    shap_values = np.asarray(
        model.get_feature_importance(pool, type="ShapValues"), dtype=float
    )
    output = []
    model_quality = max(0.0, min(1.0, 1.0 - float(metadata["metrics"]["rmse"]) / 50.0))
    for index, row in enumerate(features.to_dicts()):
        observed = float(row["observed_health"])
        predicted = float(predictions[index])
        score = float(
            np.clip(OBSERVED_WEIGHT * observed + PREDICTED_WEIGHT * predicted, 0, 100)
        )
        forecast_delta = predicted - observed
        drivers, residual = _drivers(
            row, shap_values[index], metadata["numeric_feature_medians"]
        )
        data_quality = min(1.0, float(row["months_observed"]) / 6.0) * min(
            1.0, (float(row["transaction_count"]) + float(row["invoice_count"])) / 30.0
        )
        output.append(
            {
                "entity_id": row["company_id"],
                "group_id": row["group_id"],
                "month": row["month"],
                "score": round(score, 2),
                "observed_score": round(observed, 2),
                "predicted_future_score": round(predicted, 2),
                "forecast_delta": round(forecast_delta, 2),
                "trend": "improving"
                if forecast_delta >= 3
                else "deteriorating"
                if forecast_delta <= -3
                else "stable",
                "confidence": round(0.6 * model_quality + 0.4 * data_quality, 3),
                "drivers": drivers,
                "shap_base_value": round(float(shap_values[index, -1]), 4),
                "explanation_residual": round(float(residual), 4),
                "feature_version": FEATURE_VERSION,
                "model_version": MODEL_VERSION,
                "dataset_hash": source_hash,
            }
        )
    scored = (
        pl.DataFrame(output)
        .sort("entity_id", "month")
        .with_columns(
            pl.col("score")
            .diff()
            .over("entity_id")
            .fill_null(0.0)
            .round(2)
            .alias("delta")
        )
    )
    scored = scored.with_columns(
        pl.col("trend").rle_id().over("entity_id").alias("_trend_run")
    ).with_columns(
        pl.when(pl.col("trend") == "stable")
        .then(0)
        .otherwise(pl.int_range(1, pl.len() + 1).over(["entity_id", "_trend_run"]))
        .alias("persistence_months"),
        pl.when(pl.col("trend") == "stable")
        .then(None)
        .otherwise(pl.col("month").min().over(["entity_id", "_trend_run"]))
        .alias("detected_since"),
    )
    return scored.drop("_trend_run")
