from pathlib import Path
from typing import Optional

import typer

from .io import DEFAULT_CACHE_DIR
from .params import DEFAULT_PARAMS_PATH, load_params

app = typer.Typer(no_args_is_help=True)


@app.command()
def ingest(
    input_dir: Path,
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Validate the eight CSVs and build the typed parquet cache."""
    from .io import build_cache, dataset_fingerprint

    target = build_cache(input_dir, cache_dir)
    typer.echo(f"Dataset {dataset_fingerprint(input_dir)} cached in {target}")


@app.command("fit-reference")
def fit_reference(
    input_dir: Path,
    out: Path = typer.Option(DEFAULT_PARAMS_PATH, help="Params file to write"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Measure the cohort-dependent constants and freeze them with a sha256."""
    from .reference import fit_reference as fit

    params = fit(input_dir, out, cache_dir=cache_dir)
    typer.echo(f"Wrote {out} (sha256 {params.sha256})")


def _predict(
    input_dir: Path,
    out: Path,
    export_dir: Optional[Path],
    params_path: Optional[Path],
    cache_dir: Path,
) -> None:
    from .scoring import score_dataset, write_outputs

    params = load_params(params_path)
    result = score_dataset(input_dir, params, cache_dir=cache_dir)
    paths = write_outputs(result, out)
    typer.echo(f"Wrote {result.snapshots.height} entity-months to {paths['scores']}")
    typer.echo(f"params {params.sha256[:12]} · dataset {result.dataset_hash[:12]}")
    if export_dir is not None:
        from .export import export_bundle

        manifest = export_bundle(result, export_dir)
        typer.echo(f"Wrote bundle {manifest['bundle_id'][:12]} to {export_dir}")


@app.command()
def predict(
    input_dir: Path,
    out: Path = typer.Option(Path("artifacts"), help="Output folder"),
    export_dir: Optional[Path] = typer.Option(None, help="Also write the JSON bundle here"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Score every group and company of any folder with the eight CSVs."""
    _predict(input_dir, out, export_dir, params_path, cache_dir)


@app.command(hidden=True)
def score(
    input_dir: Path,
    out: Path = typer.Option(Path("artifacts"), help="Output folder"),
    export_dir: Optional[Path] = typer.Option(None, help="Also write the JSON bundle here"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Alias of predict."""
    _predict(input_dir, out, export_dir, params_path, cache_dir)


@app.command()
def validate(
    input_dir: Path,
    out: Path = typer.Option(Path("artifacts/validation.json"), help="Report to write"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
    quick: bool = typer.Option(False, help="Skip the injection study"),
) -> None:
    """Run the label-free validation suite and write validation.json."""
    from .validation import run_validation

    report = run_validation(
        input_dir, load_params(params_path), out, cache_dir=cache_dir, quick=quick
    )
    failed = [name for name, item in report.items() if isinstance(item, dict) and item.get("pass") is False]
    typer.echo(f"Wrote {out}; failed checks: {', '.join(failed) or 'none'}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
