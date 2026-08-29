"""``sentinel`` command-line interface."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated

import typer

app = typer.Typer(help="Sentinel — evidence-driven incident intelligence", no_args_is_help=True)
eval_app = typer.Typer(help="Evaluation harness")
fault_app = typer.Typer(help="Chaos: inject / clear faults on the demo shop")
app.add_typer(eval_app, name="eval")
app.add_typer(fault_app, name="fault")


@app.command()
def api(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    """Run the HTTP API (in-process queue + scheduler unless Redis is configured)."""
    import uvicorn

    uvicorn.run("sentinel.api.app:app", host=host, port=port, reload=reload, log_config=None)


@app.command()
def worker() -> None:
    """Run the background worker (ARQ when SENTINEL_REDIS_URL is set)."""
    from sentinel.worker.main import main

    main()


@app.command()
def dev(port: int = 8000, sim_port: int = 9000, no_sim: bool = False) -> None:
    """Zero-infrastructure development stack: API + scheduler + demo shop simulator."""
    import subprocess
    import sys

    env = dict(os.environ)
    env.setdefault("SENTINEL_SIMULATOR_URL", f"http://localhost:{sim_port}")
    procs = []
    try:
        procs.append(subprocess.Popen([sys.executable, "-m", "sentinel.cli", "api", "--port", str(port)], env=env))
        if not no_sim:
            sim_env = dict(env)
            sim_env.setdefault("SIM_SENTINEL_URL", f"http://localhost:{port}")
            procs.append(subprocess.Popen([sys.executable, "-m", "sentinel_sim.cli", "run", "--port", str(sim_port)], env=sim_env))
        typer.echo(f"API on http://localhost:{port}  ·  docs http://localhost:{port}/docs" + ("" if no_sim else f"  ·  simulator http://localhost:{sim_port}"))
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


@app.command()
def migrate(revision: str = "head") -> None:
    """Apply Alembic migrations."""
    from alembic.config import Config

    from alembic import command
    from sentinel.core.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    command.upgrade(cfg, revision)


@app.command()
def bootstrap() -> None:
    """Create tables, admin user, ingest key, and the demo-shop topology."""
    from sentinel.api.bootstrap import bootstrap as _bootstrap
    from sentinel.db.session import init_schema

    async def _go() -> None:
        await init_schema()
        await _bootstrap()

    asyncio.run(_go())
    typer.echo("bootstrap complete")


@app.command()
def investigate(incident: str) -> None:
    """Run an investigation synchronously for an incident id/key (debugging aid)."""
    from sentinel.db.session import session_scope
    from sentinel.investigation.orchestrator import create_investigation, run_investigation
    from sentinel.services.incidents import get_incident

    async def _go() -> None:
        async with session_scope() as s:
            inc = await get_incident(s, incident)
            inv = await create_investigation(s, inc.id, trigger="cli")
            inv_id = inv.id
        async with session_scope() as s:
            inv = await run_investigation(s, inv_id)
            typer.echo(json.dumps(inv.summary, indent=2, default=str))

    asyncio.run(_go())


@eval_app.command("run")
def eval_run(
    name: str = "cli",
    limit: Annotated[int | None, typer.Option(help="Only run the first N scenarios")] = None,
    only: Annotated[str | None, typer.Option(help="Comma-separated substrings; run matching scenarios only")] = None,
    report: str = "docs/evaluation/latest.md",
) -> None:
    """Run the benchmark: synthesize telemetry → detect → investigate → score."""
    from sentinel.evaluation.runner import run_evaluation, write_report
    from sentinel.evaluation.scenarios import SCENARIOS

    scenarios = None
    if only:
        needles = [n.strip() for n in only.split(",") if n.strip()]
        scenarios = [s for s in SCENARIOS if any(n in s.name for n in needles)]
    summary = asyncio.run(run_evaluation(name=name, limit=limit, scenarios=scenarios))
    path = write_report(summary, report)
    typer.echo(json.dumps(summary["summary"], indent=2))
    typer.echo(f"report written to {path}")


@eval_app.command("scenarios")
def eval_scenarios() -> None:
    from sentinel.evaluation.scenarios import SCENARIOS

    for s in SCENARIOS:
        typer.echo(f"{s.name:<44} {s.fault_type:<22} {s.target:<20} → {s.expected}")
    typer.echo(f"{len(SCENARIOS)} scenarios")


@fault_app.command("inject")
def fault_inject(service: str, type_: Annotated[str, typer.Option("--type")], duration: int = 120, severity: str = "high") -> None:
    from sentinel.services.simulator_client import SimulatorClient

    out = asyncio.run(SimulatorClient().inject_fault(target=service, fault=type_, duration_s=duration, severity=severity))
    typer.echo(json.dumps(out, indent=2))


@fault_app.command("clear")
def fault_clear() -> None:
    from sentinel.services.simulator_client import SimulatorClient

    typer.echo(json.dumps(asyncio.run(SimulatorClient().clear_all())))


if __name__ == "__main__":
    app()
