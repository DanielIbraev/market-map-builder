"""CLI entrypoint for Market Map Builder.

    python -m src.main map "AI code review tools"
    python -m src.main map "AI code review tools" --num-companies 15
    python -m src.main map "AI code review tools" --vault-path ./my-vault
    python -m src.main map "AI code review tools" --mock      # free, offline
    python -m src.main refresh "AI code review tools"

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import time

import typer

from .refresh import refresh_sector
from .research import research_sector
from .vault_writer import write_vault

app = typer.Typer(
    add_completion=False,
    help="Research a tech sector into an interlinked Obsidian vault.",
)

DEFAULT_VAULT = "./vault"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _console():
    try:
        from rich.console import Console  # type: ignore

        return Console()
    except Exception:
        return None


def _err(msg: str) -> None:
    c = _console()
    if c is not None:
        c.print("[bold red]Error:[/bold red] " + msg)
    else:
        typer.echo("Error: " + msg, err=True)


def _summary(title: str, lines) -> None:
    c = _console()
    if c is not None:
        from rich.panel import Panel  # type: ignore

        c.print(Panel("\n".join(lines), title=title, border_style="green", expand=False))
    else:
        typer.echo("\n== %s ==" % title)
        for ln in lines:
            typer.echo(_plain(ln))


def _plain(s: str) -> str:
    import re

    return re.sub(r"\[/?[a-zA-Z0-9 =#]+\]", "", s)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def map(
    sector: str = typer.Argument(..., help="Sector or company name, e.g. \"AI code review tools\"."),
    num_companies: int = typer.Option(12, "--num-companies", "-n", help="Target number of companies (4-25)."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path", help="Output vault directory."),
    mock: bool = typer.Option(False, "--mock", help="Offline sample data — no API key or cost."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output."),
) -> None:
    """Research SECTOR and build a fresh Obsidian market map."""
    start = time.perf_counter()
    try:
        research = research_sector(sector, num_companies=num_companies, mock=mock, quiet=quiet)
        result = write_vault(research, vault_path=vault_path, quiet=quiet)
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    except RuntimeError as exc:
        _err(str(exc))
        raise typer.Exit(1)

    elapsed = time.perf_counter() - start
    lines = [
        "Sector:      [bold]%s[/bold]" % research.sector_name,
        "Companies:   [bold]%d[/bold] researched (%s)" % (len(research.companies), research.source),
        "Hub note:    %s" % result["hub_path"],
        "Vault dir:   %s" % result["sector_dir"],
        "Elapsed:     %.1fs" % elapsed,
    ]
    broken = result.get("broken_links") or []
    if broken:
        lines.append("[yellow]Broken links: %d (see warnings above)[/yellow]" % len(broken))
    _summary("Market map built", lines)


@app.command()
def refresh(
    sector: str = typer.Argument(..., help="Existing sector to re-research and diff."),
    num_companies: int = typer.Option(12, "--num-companies", "-n", help="Target number of companies (4-25)."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path", help="Vault directory to refresh."),
    mock: bool = typer.Option(False, "--mock", help="Offline sample data — no API key or cost."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output."),
) -> None:
    """Re-research SECTOR and diff the results into an existing vault."""
    start = time.perf_counter()
    try:
        result = refresh_sector(
            sector, vault_path=vault_path, num_companies=num_companies, mock=mock, quiet=quiet
        )
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    except RuntimeError as exc:
        _err(str(exc))
        raise typer.Exit(1)

    elapsed = time.perf_counter() - start
    updated = result.get("updated") or []
    lines = [
        "Mode:        [bold]%s[/bold]" % result["mode"],
        "Added:       %d" % len(result.get("added") or []),
        "Updated:     %d" % len(updated),
        "Unchanged:   %d" % len(result.get("unchanged") or []),
        "Retained:    %d" % len(result.get("retained") or []),
        "Hub note:    %s" % result["hub_path"],
        "Elapsed:     %.1fs" % elapsed,
    ]
    broken = result.get("broken_links") or []
    if broken:
        lines.append("[yellow]Broken links: %d[/yellow]" % len(broken))
    _summary("Refresh complete", lines)


if __name__ == "__main__":
    app()
