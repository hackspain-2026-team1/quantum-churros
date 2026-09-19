from pathlib import Path
from typing import Annotated

import typer
from sqlmodel import Session, create_engine

from .config import settings
from .industry import run_classification
from .ingest import dataset_fingerprint, ingest_dataset, source_paths
from .publish import publish_outputs

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Manage the PostgreSQL data lifecycle for Embat X-Ray."""


@app.command()
def ingest(input_dir: Annotated[Path, typer.Argument()] = Path("data/raw"), dry_run: bool = False) -> None:
    """Load an immutable challenge dataset into PostgreSQL with an idempotent content hash."""
    paths = source_paths(input_dir)
    if dry_run:
        fingerprint = dataset_fingerprint(paths)
        typer.echo(f"Validated {len(paths)} files; dataset hash: {fingerprint}")
        return
    fingerprint, row_counts, skipped = ingest_dataset(input_dir, settings.database_url)
    if skipped:
        typer.echo(f"Dataset {fingerprint} is already loaded; no rows changed")
        return
    typer.echo(f"Loaded dataset {fingerprint}: {row_counts}")


@app.command()
def classify(
    input_dir: Annotated[Path, typer.Argument()] = Path("data/raw"),
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Classify companies into industry archetypes for a dataset version."""
    db_engine = create_engine(settings.database_url, pool_pre_ping=True)
    with Session(db_engine) as session:
        dataset_hash, counts, skipped = run_classification(
            session,
            input_dir,
            force=force,
            dry_run=dry_run,
        )
    if skipped:
        typer.echo(
            f"Dataset {dataset_hash} already classified with rules-v1; use --force to re-run"
        )
        return
    if dry_run:
        typer.echo(f"Dry run for dataset {dataset_hash}:")
    else:
        typer.echo(f"Classified dataset {dataset_hash}:")
    for slug, total in counts.items():
        typer.echo(f"  {slug}: {total}")


if __name__ == "__main__":
    app()


@app.command()
def publish(out_dir: Annotated[Path, typer.Argument()] = Path("artifacts/full")) -> None:
    """Load an engine run (panel, scores, alerts) into the xray schema, one attribute per column."""
    dataset_hash, counts = publish_outputs(out_dir, settings.database_url)
    typer.echo(f"Published dataset {dataset_hash}: {counts}")
