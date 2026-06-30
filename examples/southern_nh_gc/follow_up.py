#!/usr/bin/env python3
"""Southern NH GC follow-up check — leads needing outreach or quote follow-up.

Run manually::

    uv run python examples/southern_nh_gc/follow_up.py

Schedule (weekdays 4 PM)::

    jarvis scheduler create "Southern NH GC follow-ups" \\
        --type cron --value "0 21 * * 1-5"
"""

from __future__ import annotations

from datetime import datetime, timezone

import click


@click.command()
@click.option(
    "--stale-days",
    default=3,
    show_default=True,
    help="Flag leads with no update after this many days.",
)
@click.option(
    "--model",
    default=None,
    help="Model to use (e.g. qwen3:8b).",
)
@click.option(
    "--engine",
    "engine_key",
    default=None,
    help="Engine backend (e.g. ollama).",
)
def main(stale_days: int, model: str | None, engine_key: str | None) -> None:
    """Review stored leads and list follow-ups due today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    prompt = (
        f"Today is {today}. You are following up for a southern NH general "
        "contractor (decks, garages, additions).\n\n"
        f"1. Use memory_search to list all leads you have stored (status "
        f"new, contacted, or quoted).\n"
        f"2. Flag any lead with no update in {stale_days}+ days.\n"
        "3. For each follow-up due, suggest a specific action: call, text, "
        "email template, or mark lost.\n"
        "4. Update memory_store with any status changes the user would make "
        "after acting.\n\n"
        "Output format:\n"
        "## Follow-ups due today\n"
        "- [lead_id] — [town] — [job] — last touch [date] — **Action**: ...\n\n"
        "## Pipeline summary\n"
        "- New: N | Contacted: N | Quoted: N | Won: N | Lost: N\n\n"
        "## Suggested outreach (copy-paste)\n"
        "Short text/email templates for the top 3 follow-ups."
    )

    try:
        from openjarvis import Jarvis

        kwargs: dict[str, str | None] = {}
        if model:
            kwargs["model"] = model
        if engine_key:
            kwargs["engine_key"] = engine_key

        j = Jarvis(**kwargs)  # type: ignore[arg-type]
    except Exception as exc:
        click.echo(
            f"Error: Could not initialize Jarvis: {exc}\n\n"
            "Make sure an inference engine is running and openjarvis is installed.",
            err=True,
        )
        raise SystemExit(1) from exc

    try:
        response = j.ask(
            prompt,
            agent="operative",
            tools=["memory_search", "memory_store", "think"],
        )
    except Exception as exc:
        click.echo(f"Error during follow-up check: {exc}", err=True)
        raise SystemExit(1) from exc
    finally:
        j.close()

    click.echo(f"\n{'=' * 60}")
    click.echo(f"  Southern NH GC Follow-ups — {today}")
    click.echo(f"{'=' * 60}\n")
    click.echo(response)
    click.echo(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
