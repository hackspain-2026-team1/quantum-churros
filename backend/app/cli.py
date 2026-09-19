from pathlib import Path
from typing import Annotated

import typer
from sqlmodel import Session, create_engine

from .config import settings
from .demo_notifications import dispatch_demo_notifications
from .industry import run_classification
from .ingest import dataset_fingerprint, ingest_dataset, source_paths
from .pipeline import sync_dataset
from .publish import publish_outputs

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Manage the PostgreSQL data lifecycle for Embat X-Ray."""


@app.command()
def ingest(
    input_dir: Annotated[Path, typer.Argument()] = Path("data/raw"),
    dry_run: bool = False,
) -> None:
    """Load an immutable challenge dataset into PostgreSQL with an idempotent content hash."""
    paths = source_paths(input_dir)
    if dry_run:
        fingerprint = dataset_fingerprint(paths)
        typer.echo(f"Validated {len(paths)} files; dataset hash: {fingerprint}")
        return
    fingerprint, row_counts, skipped = ingest_dataset(
        input_dir, settings.require_database_url()
    )
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
    db_engine = create_engine(settings.require_database_url(), pool_pre_ping=True)
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


@app.command()
def publish(
    out_dir: Annotated[Path, typer.Argument()] = Path("artifacts/full"),
) -> None:
    """Load an engine run (panel, scores, alerts) into the xray schema, one attribute per column."""
    dataset_hash, counts = publish_outputs(out_dir, settings.require_database_url())
    typer.echo(f"Published dataset {dataset_hash}: {counts}")


@app.command()
def sync(
    input_dir: Annotated[Path, typer.Argument()] = Path("data/raw"),
    out_dir: Path = typer.Option(Path("artifacts"), help="Parquet artifact directory"),
    bundle_dir: Path | None = typer.Option(None, help="JSON bundle directory"),
    evidence_months: int = typer.Option(24, min=0),
) -> None:
    """Ingest, classify, score, publish, and export one immutable dataset version."""
    target_bundle = bundle_dir or settings.bundle_dir
    typer.echo("Synchronizing source data, model outputs, and read projections")
    result = sync_dataset(
        input_dir=input_dir,
        out_dir=out_dir,
        bundle_dir=target_bundle,
        database_url=settings.require_database_url(),
        evidence_months=evidence_months,
    )
    ingest_state = "already loaded" if result.ingest_skipped else "loaded"
    classification_state = (
        "already classified" if result.classification_skipped else "classified"
    )
    typer.echo(
        f"Dataset {result.dataset_hash}: {ingest_state}, {classification_state}, "
        f"published {result.published_counts}, bundle {result.bundle_id[:12]}"
    )


@app.command("notify-demo")
def notify_demo(
    bundle_dir: Annotated[Path | None, typer.Argument()] = None,
    month: Annotated[
        str | None, typer.Option(help="Closing month YYYY-MM; latest fired by default")
    ] = None,
    clear: Annotated[bool, typer.Option(help="Clear Mailpit before sending")] = True,
) -> None:
    """Send one close's routed demo alerts to the configured Mailpit SMTP sink."""
    selected, count = dispatch_demo_notifications(
        bundle_dir or settings.bundle_dir,
        month=month,
        clear=clear,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        sender=settings.notification_from,
        frontend_base_url=settings.frontend_base_url,
        mailpit_api_url=settings.mailpit_api_url,
    )
    typer.echo(f"Captured {count} demo emails for {selected} in Mailpit")


if __name__ == "__main__":
    app()
