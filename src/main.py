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

import os

from .digest import run_digest
from .export import export_sector
from .memo import write_memo
from .refresh import refresh_sector
from .research import research_sector, validate_query
from .vault_writer import write_vault
from . import watchlist as wl

app = typer.Typer(
    add_completion=False,
    help="Research a tech sector into an interlinked Obsidian vault.",
)
watch_app = typer.Typer(add_completion=False, help="Track sectors + portfolio companies.")
app.add_typer(watch_app, name="watchlist")

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
        result = write_vault(
            research, vault_path=vault_path, quiet=quiet,
            portfolio=wl.portfolio_slugs(vault_path),
        )
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
            sector, vault_path=vault_path, num_companies=num_companies, mock=mock,
            quiet=quiet, portfolio=wl.portfolio_slugs(vault_path),
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


@app.command()
def digest(
    sector: str = typer.Argument(..., help="Sector to refresh and summarize."),
    num_companies: int = typer.Option(12, "--num-companies", "-n"),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
    mock: bool = typer.Option(False, "--mock", help="Offline sample data — no API key or cost."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    webhook: str = typer.Option(
        None, "--webhook",
        help="HTTPS Slack-compatible webhook to deliver the digest to "
             "(or set MARKET_MAP_WEBHOOK).",
    ),
) -> None:
    """Refresh SECTOR and produce a 'what moved' digest (weekly-cron friendly)."""
    start = time.perf_counter()
    webhook = webhook or os.environ.get("MARKET_MAP_WEBHOOK")
    try:
        out = run_digest(
            sector, vault_path=vault_path, num_companies=num_companies,
            mock=mock, quiet=quiet, webhook=webhook,
            portfolio=wl.portfolio_slugs(vault_path),
        )
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc))
        raise typer.Exit(2)
    except RuntimeError as exc:
        _err(str(exc))
        raise typer.Exit(1)

    if not quiet:
        typer.echo("")
        typer.echo(out["text"])
    res = out["result"]
    lines = [
        "Added / updated: [bold]%d / %d[/bold]" % (len(res["added"]), len(res["updated"])),
        "Digest note:  %s" % out["digest_path"],
        "Elapsed:      %.1fs" % (time.perf_counter() - start),
    ]
    if webhook:
        lines.append("Webhook:      %s" % ("delivered" if out["delivered"] else "[red]FAILED[/red]"))
    _summary("Digest complete", lines)


@app.command()
def export(
    sector: str = typer.Argument(..., help="Sector already mapped in the vault."),
    fmt: str = typer.Option("csv", "--format", "-f", help="csv or json."),
    out: str = typer.Option(None, "--out", "-o", help="Output file path (default: inside the sector folder)."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
) -> None:
    """Export a sector's data from the vault to CSV/JSON (offline, no API)."""
    try:
        validate_query(sector)
        path = export_sector(sector, vault_path=vault_path, fmt=fmt, out_path=out)
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc))
        raise typer.Exit(2)
    _summary("Export complete", ["Wrote: [bold]%s[/bold]" % path])


@app.command()
def memo(
    sector: str = typer.Argument(..., help="Sector already mapped in the vault."),
    company: str = typer.Argument(..., help="Company (name or slug) within that sector."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
    mock: bool = typer.Option(False, "--mock", help="Skip the API; grounded template memo only."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Draft a first-pass deal memo for COMPANY, grounded in the vault notes."""
    start = time.perf_counter()
    try:
        validate_query(sector)
        validate_query(company)
        path = write_memo(sector, company, vault_path=vault_path, mock=mock, quiet=quiet)
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc))
        raise typer.Exit(2)
    except RuntimeError as exc:
        _err(str(exc))
        raise typer.Exit(1)
    _summary("Memo drafted", [
        "Memo: [bold]%s[/bold]" % path,
        "Elapsed: %.1fs" % (time.perf_counter() - start),
        "[dim]Draft only — verify every figure before circulating.[/dim]",
    ])


# ---------------------------------------------------------------------------
# Watchlist / portfolio / overlay
# ---------------------------------------------------------------------------

@watch_app.command("add")
def watchlist_add(
    sector: str = typer.Argument(..., help="Sector to track."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
) -> None:
    """Track a sector (refreshed by `watchlist run`)."""
    try:
        sector = validate_query(sector)
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    added = wl.add_item(vault_path, "sectors", sector)
    typer.echo("Tracking sector: %s" % sector if added else "Already tracked: %s" % sector)


@watch_app.command("rm")
def watchlist_rm(
    sector: str = typer.Argument(...),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
) -> None:
    """Stop tracking a sector."""
    removed = wl.remove_item(vault_path, "sectors", sector)
    typer.echo("Removed: %s" % sector if removed else "Not on the watchlist: %s" % sector)


@watch_app.command("show")
def watchlist_show(
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
) -> None:
    """Show tracked sectors and portfolio companies."""
    data = wl.load_watchlist(vault_path)
    typer.echo("Sectors (%d):" % len(data["sectors"]))
    for s in data["sectors"]:
        typer.echo("  - %s" % s)
    typer.echo("Portfolio (%d):" % len(data["portfolio"]))
    for p in data["portfolio"]:
        typer.echo("  - %s" % p)
    if not data["sectors"] and not data["portfolio"]:
        typer.echo("  (empty — try: watchlist add \"AI coding assistants\")")


@watch_app.command("run")
def watchlist_run(
    num_companies: int = typer.Option(12, "--num-companies", "-n"),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
    mock: bool = typer.Option(False, "--mock", help="Offline sample data — no API key or cost."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    webhook: str = typer.Option(None, "--webhook", help="HTTPS webhook for the combined digest."),
) -> None:
    """Refresh + digest every tracked sector in one pass (cron-friendly)."""
    start = time.perf_counter()
    webhook = webhook or os.environ.get("MARKET_MAP_WEBHOOK")
    try:
        out = wl.run_watchlist(
            vault_path=vault_path, num_companies=num_companies,
            mock=mock, quiet=quiet, webhook=webhook,
        )
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc))
        raise typer.Exit(2)
    except RuntimeError as exc:
        _err(str(exc))
        raise typer.Exit(1)
    lines = [
        "Sectors run:  [bold]%d[/bold]" % len(out["sectors"]),
        "Digest:       %s" % out["digest_path"],
        "Elapsed:      %.1fs" % (time.perf_counter() - start),
    ]
    if webhook:
        lines.append("Webhook:      %s" % ("delivered" if out["delivered"] else "[red]FAILED[/red]"))
    _summary("Watchlist run complete", lines)


@app.command()
def portfolio(
    action: str = typer.Argument(..., help="add | rm"),
    company: str = typer.Argument(..., help="Portfolio company name."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
) -> None:
    """Manage portfolio companies (starred in hubs; used by `overlay`)."""
    action = action.strip().lower()
    if action not in ("add", "rm"):
        _err("Action must be 'add' or 'rm'.")
        raise typer.Exit(2)
    try:
        company = validate_query(company)
    except ValueError as exc:
        _err(str(exc))
        raise typer.Exit(2)
    if action == "add":
        done = wl.add_item(vault_path, "portfolio", company)
        typer.echo("Portfolio + %s" % company if done else "Already in portfolio: %s" % company)
    else:
        done = wl.remove_item(vault_path, "portfolio", company)
        typer.echo("Portfolio - %s" % company if done else "Not in portfolio: %s" % company)


@app.command()
def overlay(
    company: str = typer.Argument(None, help="Company to locate (default: whole portfolio)."),
    vault_path: str = typer.Option(DEFAULT_VAULT, "--vault-path"),
    days: int = typer.Option(30, "--days", help="How recent a rival move counts as 'recent'."),
) -> None:
    """Where does a (portfolio) company sit? Maps, rivals, and recent rival moves."""
    try:
        if company:
            names = [validate_query(company)]
        else:
            names = wl.load_watchlist(vault_path)["portfolio"]
            if not names:
                _err("Portfolio is empty — add one with: portfolio add \"<company>\" "
                     "or pass a company name.")
                raise typer.Exit(2)
        for name in names:
            report = wl.overlay(name, vault_path=vault_path, recent_days=days)
            typer.echo(wl.render_overlay(report))
    except (ValueError, FileNotFoundError) as exc:
        _err(str(exc))
        raise typer.Exit(2)


if __name__ == "__main__":
    app()
