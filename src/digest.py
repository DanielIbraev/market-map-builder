"""Change digest — turn a refresh run into a shareable "what moved this week".

`run_digest()` refreshes a sector, renders a markdown digest of what changed
(added / updated / not re-found, with freshness flags), writes it into the
vault, and can POST it to a Slack-compatible webhook.

Scheduling is deliberately external (cron/launchd — see README): this stays a
simple, auditable command with no daemon.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import slugify
from .refresh import refresh_sector


def run_digest(
    sector: str,
    vault_path: str = "./vault",
    num_companies: int = 12,
    mock: bool = False,
    quiet: bool = False,
    webhook: Optional[str] = None,
    portfolio=None,
) -> Dict[str, object]:
    """Refresh + render + persist a digest. Returns {digest_path, text, result}."""
    result = refresh_sector(
        sector, vault_path=vault_path, num_companies=num_companies,
        mock=mock, quiet=quiet, portfolio=portfolio,
    )
    text = render_digest(sector, result)

    date = datetime.now(timezone.utc).date().isoformat()
    sector_dir = str(result["sector_dir"])
    digest_path = os.path.join(sector_dir, "_digest-%s.md" % date)
    with open(digest_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    delivered = False
    if webhook:
        delivered = post_webhook(webhook, text)

    return {"digest_path": digest_path, "text": text, "result": result, "delivered": delivered}


def render_digest(sector: str, result: Dict[str, object]) -> str:
    """Markdown digest from a refresh_sector() result."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added: List[str] = list(result.get("added") or [])
    updated = list(result.get("updated") or [])
    retained: List[str] = list(result.get("retained") or [])
    unchanged: List[str] = list(result.get("unchanged") or [])

    lines = [
        "# %s — change digest · %s" % (sector, date),
        "",
        "**%d added · %d updated · %d unchanged · %d not re-found**" % (
            len(added), len(updated), len(unchanged), len(retained)),
        "",
    ]

    if added:
        lines += ["## New entrants", ""]
        for name in added:
            lines.append("- **%s** — added to the map ([[%s]])" % (name, slugify(name)))
        lines.append("")

    if updated:
        lines += ["## Moved", ""]
        for name, changes in updated:
            lines.append("- **%s** — %s ([[%s]])" % (name, "; ".join(changes), slugify(name)))
        lines.append("")

    if retained:
        lines += [
            "## Not re-found this run",
            "",
            "_Still in the map, but this run's research didn't surface them — "
            "worth a manual check (pivot, rename, shutdown?):_",
            "",
        ]
        for name in retained:
            lines.append("- [[%s|%s]]" % (slugify(name), name))
        lines.append("")

    if not added and not updated and not retained:
        lines += ["_No movement detected — the map matches the latest research._", ""]

    broken = list(result.get("broken_links") or [])
    if broken:
        lines += ["> ⚠️ %d broken wikilink(s) detected after refresh." % len(broken), ""]

    lines.append("_Full map: [[%s]]_" % os.path.basename(str(result["hub_path"]))[:-3])
    lines.append("")
    return "\n".join(lines)


def post_webhook(url: str, text: str) -> bool:
    """POST {'text': digest} to a Slack-compatible webhook. HTTPS only."""
    if not url.lower().startswith("https://"):
        raise ValueError("Webhook URL must be https://")
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False
