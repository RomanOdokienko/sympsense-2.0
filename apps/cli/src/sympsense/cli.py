from __future__ import annotations

import json
from pathlib import Path

import typer

from sympsense.downstream_export import build_downstream_export
from sympsense.patient_briefing import build_patient_briefing
from sympsense.problem_list import build_problem_list
from sympsense.selfcheck import run_selfcheck

app = typer.Typer(help="Sympsense CLI (agent-first scaffold)")


@app.command("status")
def status() -> None:
    """Scaffold status command."""
    typer.echo("sympsense: scaffold ready")


@app.command("serve-api")
def serve_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run local read-only API over canonical/facts JSON."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "uvicorn is not installed. Run 'pip install -e .'."
        ) from exc

    uvicorn.run("sympsense.api_server:app", host=host, port=port, reload=reload)


@app.command("selfcheck")
def selfcheck(
    write_report: bool = True,
) -> None:
    """Run integrated system self-check and print JSON summary."""
    report = run_selfcheck(project_root=Path(".").resolve(), write_report=write_report)
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@app.command("export-downstream")
def export_downstream(
    include_graph: bool = False,
    write_report: bool = True,
) -> None:
    """Build stable downstream export payload from canonical/facts."""
    report = build_downstream_export(
        project_root=Path(".").resolve(),
        include_graph=include_graph,
        write_report=write_report,
    )
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@app.command("patient-briefing")
def patient_briefing(
    write_report: bool = True,
) -> None:
    """Build patient briefing report (JSON + HTML)."""
    report = build_patient_briefing(
        project_root=Path(".").resolve(),
        write_report=write_report,
    )
    typer.echo(json.dumps(report, ensure_ascii=True, indent=2))


@app.command("problem-list")
def problem_list(
    write_report: bool = True,
) -> None:
    """Build curated clinical problem list (stable/episodic/symptom/uncertain)."""
    report = build_problem_list(
        project_root=Path(".").resolve(),
        write_report=write_report,
    )
    typer.echo(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    app()
