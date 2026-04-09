from __future__ import annotations

import typer

app = typer.Typer(help="Sympsense CLI (agent-first scaffold)")


@app.command("status")
def status() -> None:
    """Scaffold status command."""
    typer.echo("sympsense: scaffold ready")


if __name__ == "__main__":
    app()

