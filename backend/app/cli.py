from pathlib import Path
from typing import Annotated

import typer

from .config import settings
from .ingest import dataset_fingerprint, ingest_dataset, source_paths

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


if __name__ == "__main__":
    app()
