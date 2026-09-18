from pathlib import Path

import typer

from .scoring import score_dataset

app = typer.Typer(no_args_is_help=True)


@app.command()
def score(input_dir: Path, output: Path = Path("artifacts/scores.parquet")) -> None:
    """Score every company and month from a compatible dataset directory."""
    frame = score_dataset(input_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".csv":
        frame.write_csv(output)
    else:
        frame.write_parquet(output)
    typer.echo(f"Wrote {frame.height} score snapshots to {output}")


if __name__ == "__main__":
    app()
