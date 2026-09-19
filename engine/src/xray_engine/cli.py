from pathlib import Path
from typing import Optional

import typer

from .io import DEFAULT_CACHE_DIR
from .params import DEFAULT_PARAMS_PATH, ParamsError, load_params

app = typer.Typer(no_args_is_help=True)


def _params(path: Optional[Path]):
    # a params file whose sha256 does not match its content is refused
    try:
        return load_params(path)
    except ParamsError as error:
        typer.echo(f"Parámetros rechazados: {error}", err=True)
        raise typer.Exit(code=2) from error


@app.command()
def ingest(
    input_dir: str,
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Validate the eight CSVs and build the typed parquet cache."""
    from .io import build_cache, dataset_fingerprint

    target = build_cache(Path(input_dir), cache_dir)
    typer.echo(f"Dataset {dataset_fingerprint(Path(input_dir))} cached in {target}")


@app.command("fit-reference")
def fit_reference(
    input_dir: str,
    out: Path = typer.Option(DEFAULT_PARAMS_PATH, help="Params file to write"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
    report: Path = typer.Option(
        Path("artifacts/fit_reference_report.json"), help="Fit report (aggregates only)"
    ),
) -> None:
    """Measure the cohort-dependent constants and freeze them with a sha256."""
    import json

    from .reference import fit_reference as fit

    params = fit(input_dir, out, cache_dir=cache_dir, report_path=report)
    typer.echo(f"Wrote {out} (sha256 {params.sha256})")
    summary = json.loads(report.read_text(encoding="utf-8"))
    for band, item in summary["liquidity_bands"].items():
        pooled = f" + {', '.join(item['pooled_with'])}" if item["pooled_with"] else ""
        days = " ".join(f"{key}={value}" for key, value in item["quantiles_days"].items())
        typer.echo(f"  liquidity {band}{pooled}: {item['pooled_group_months']} group-months · {days}")
    medians = " ".join(f"{key}={value}" for key, value in summary["reference_medians"].items())
    typer.echo(f"  reference medians: {medians}")
    for name, item in summary["calibration"]["tables"].items():
        if not item.get("group_months"):
            continue
        landed = " ".join(f"{key}->{value}" for key, value in item["score_at_quantiles"].items())
        verdict = "ok" if item["acceptable"] else "REVIEW"
        typer.echo(
            f"  {name}: {landed} · at 0 {item['at_0_share']:.1%} · at 100 {item['at_100_share']:.1%} · {verdict}"
        )
    typer.echo(f"Wrote {report}")


def _predict(
    input_dir: str,
    out: Path,
    export_dir: Optional[Path],
    params_path: Optional[Path],
    cache_dir: Path,
    evidence_months: int = 24,
) -> None:
    from .scoring import score_dataset, write_outputs

    params = _params(params_path)
    result = score_dataset(input_dir, params, cache_dir=cache_dir)
    paths = write_outputs(result, out)
    typer.echo(f"Wrote {result.snapshots.height} entity-months to {paths['scores']}")
    typer.echo(f"params {params.sha256[:12]} · dataset {result.dataset_hash[:12]}")
    if export_dir is not None:
        from .export import DEFAULT_VALIDATION_PATH, export_from_result

        # the receipt is the validation report of the same output folder, else the default one;
        # a report of other params or another dataset is told apart inside the receipt
        own = out / "validation.json"
        manifest = export_from_result(
            result, export_dir, validation_path=own if own.is_file() else DEFAULT_VALIDATION_PATH,
            evidence_months=evidence_months,
        )
        typer.echo(f"Wrote bundle {manifest['bundle_id'][:12]} to {export_dir}")


@app.command()
def predict(
    input_dir: str,
    out: Path = typer.Option(Path("artifacts"), help="Output folder"),
    export_dir: Optional[Path] = typer.Option(None, help="Also write the JSON bundle here"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
    evidence_months: int = typer.Option(24, min=0, help="Months of evidence kept per entity in the bundle"),
) -> None:
    """Score every group and company of any folder with the eight CSVs."""
    _predict(input_dir, out, export_dir, params_path, cache_dir, evidence_months)


@app.command(hidden=True)
def score(
    input_dir: str,
    out: Path = typer.Option(Path("artifacts"), help="Output folder"),
    export_dir: Optional[Path] = typer.Option(None, help="Also write the JSON bundle here"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
    evidence_months: int = typer.Option(24, min=0, help="Months of evidence kept per entity in the bundle"),
) -> None:
    """Alias of predict."""
    _predict(input_dir, out, export_dir, params_path, cache_dir, evidence_months)


@app.command()
def export(
    input_dir: str,
    export_dir: Path = typer.Option(Path("frontend/static/data/v1"), help="Bundle folder"),
    receipt: Optional[Path] = typer.Option(
        None, help="validation.json to embed as the receipt (default: artifacts/validation.json when present)"
    ),
    evidence_months: int = typer.Option(24, min=0, help="Months of evidence kept per entity"),
    generated_at: Optional[str] = typer.Option(None, help="Manifest stamp (default: extraction date of the dataset)"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
) -> None:
    """Score a folder and write only the static JSON bundle."""
    from .export import DEFAULT_VALIDATION_PATH, export_from_result
    from .scoring import score_dataset

    if receipt is not None and not receipt.is_file():
        typer.echo(f"No existe el informe de validación {receipt}", err=True)
        raise typer.Exit(code=2)
    result = score_dataset(input_dir, _params(params_path), cache_dir=cache_dir)
    manifest = export_from_result(
        result, export_dir, validation_path=receipt or DEFAULT_VALIDATION_PATH,
        evidence_months=evidence_months, generated_at=generated_at,
    )
    typer.echo(f"Wrote bundle {manifest['bundle_id'][:12]} to {export_dir}")


@app.command()
def forecast(
    artifacts: Path = typer.Option(Path("artifacts"), help="Folder with scores.parquet and panel.parquet from predict"),
    bundle: Path = typer.Option(..., help="Bundle folder written by predict --export-dir"),
    out: Path = typer.Option(..., help="Output folder for the horizons (rumbo/horizons)"),
    past: Optional[str] = typer.Option("2025-03:", help="Past cuts to forecast out of sample, FROM:TO (empty TO = up to the cut)"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
) -> None:
    """Train the score forecast on the scored history, validate it out of time and write the horizons."""
    from .forecast import mindex, prever

    pasados = None
    if past:
        a, _, b = past.partition(":")
        pasados = (mindex(a), mindex(b) if b else 10**6)
    index = prever(artifacts, bundle, _params(params_path), out, pasados=pasados, log=typer.echo)
    ref = index["validation"].get("corte_de_referencia")
    if ref:
        typer.echo(
            f"Validation at {ref['corte']} (3 and 6 months): median error {ref['error_mediana']} points "
            f"vs {ref['error_sin_cambio']} if nothing changes; 80 % band covers {ref['acierta_80']:.0%}"
        )
    typer.echo(f"Wrote horizons for {len(index['entities'])} entities to {out}")


@app.command()
def validate(
    input_dir: str,
    out: Path = typer.Option(Path("artifacts/validation.json"), help="Report to write"),
    params_path: Optional[Path] = typer.Option(None, "--params", help="Params file"),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, help="Parquet cache root"),
    quick: bool = typer.Option(False, help="Skip the injection study"),
) -> None:
    """Run the label-free validation suite and write validation.json."""
    from .validation import run_validation

    report = run_validation(
        input_dir, _params(params_path), out, cache_dir=cache_dir, quick=quick
    )
    failed = [name for name, item in report.items() if isinstance(item, dict) and item.get("pass") is False]
    typer.echo(f"Wrote {out}; failed checks: {', '.join(failed) or 'none'}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
