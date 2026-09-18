from pathlib import Path

import typer

from .features import build_monthly_features
from .modeling import dataset_hash, train_model
from .scoring import score_dataset

app = typer.Typer(no_args_is_help=True)


@app.command()
def train(
    input_dir: Path,
    model_dir: Path = Path("artifacts/model"),
    iterations: int = typer.Option(500, min=50),
    seed: int = 42,
) -> None:
    """Train and validate the temporal model, then persist it with SHAP metadata."""
    features = build_monthly_features(input_dir, include_targets=True)
    metadata = train_model(
        features, model_dir, dataset_hash(input_dir), iterations=iterations, seed=seed
    )
    typer.echo(f"Wrote {metadata['model_version']} to {model_dir}")
    typer.echo(f"Validation metrics: {metadata['metrics']}")


@app.command()
def score(
    input_dir: Path,
    model_dir: Path = Path("artifacts/model"),
    output: Path = Path("artifacts/scores.parquet"),
) -> None:
    """Score every company and month with a persisted temporal model."""
    frame = score_dataset(input_dir, model_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".csv":
        frame.write_csv(output)
    else:
        frame.write_parquet(output)
    typer.echo(f"Wrote {frame.height} score snapshots to {output}")


if __name__ == "__main__":
    app()
