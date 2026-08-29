"""``sentinel-sim`` — run the demo shop, inject faults, deploy releases."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import typer

from sentinel_sim.config import settings

app = typer.Typer(help="Sentinel Demo Shop simulator", no_args_is_help=True)


@app.command()
def run(port: int = typer.Option(None, help="control-plane port (default SIM_CONTROL_PORT)"), host: str | None = None) -> None:
    """Start the control plane and all seven services (one process, one port per service)."""
    import uvicorn

    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if host:
        settings.host = host
    uvicorn.run("sentinel_sim.control:app", host="0.0.0.0", port=port or settings.control_port, log_level="warning", access_log=False)


def _control() -> str:
    return f"http://127.0.0.1:{settings.control_port}"


@app.command()
def inject(target: str, fault: str, duration: int = 120, severity: str = "high") -> None:
    r = httpx.post(_control() + "/faults", json={"target": target, "fault": fault, "duration_s": duration, "severity": severity}, timeout=10)
    typer.echo(json.dumps(r.json(), indent=2))


@app.command()
def clear() -> None:
    typer.echo(json.dumps(httpx.delete(_control() + "/faults", timeout=10).json()))


@app.command()
def deploy(service: str, fault: str | None = None) -> None:
    r = httpx.post(_control() + "/releases/deploy", json={"service": service, "fault": fault}, timeout=10)
    typer.echo(json.dumps(r.json(), indent=2))


@app.command()
def rollback(service: str) -> None:
    r = httpx.post(_control() + "/releases/rollback", json={"service": service}, timeout=10)
    typer.echo(json.dumps(r.json(), indent=2))


@app.command()
def status() -> None:
    typer.echo(json.dumps(httpx.get(_control() + "/health", timeout=10).json(), indent=2))


@app.command()
def scenario(name: str = typer.Argument(..., help="e.g. 17 or payment-pool")) -> None:
    """Run a multi-step chaos scenario (see docs/runbooks/chaos-scenarios.md)."""
    from sentinel_sim.scenarios import run_scenario

    asyncio.run(run_scenario(name))


if __name__ == "__main__":
    app()
