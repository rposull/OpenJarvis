#!/usr/bin/env python3
"""Generate a customer quote PDF/HTML for the 22×8 covered porch job.

Usage::

    python3 examples/southern_nh_gc/create_porch_quote.py
    python3 examples/southern_nh_gc/create_porch_quote.py --client "Smith" --town Nashua
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_REPO = _ROOT.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scope_templates import DEFAULT_EXCLUSIONS, covered_porch_scope, default_timeline
from openjarvis.construction.documents import (
    LineItem,
    compute_quote_totals,
    render_and_save,
    render_quote_html,
)

COMPANY = "O'Sullivan Construction & Property Management"
PHONE = "(978) 888-8068"
EMAIL = "rposull@hotmail.com"

# 22 × 8 ft covered porch — customer all-in target ~$145/sqft
WIDTH_FT = 22
DEPTH_FT = 8
SQFT = WIDTH_FT * DEPTH_FT
CUSTOMER_RATE_SQFT = 145.0
MATERIALS_RATE_SQFT = 75.0
LABOR_RATE_SQFT = 70.0


def porch_quote_items() -> list[LineItem]:
    return [
        LineItem(
            description=(
                f"Covered porch — materials ({WIDTH_FT}×{DEPTH_FT} ft, {SQFT} sq ft): "
                "PT framing lumber, composite decking and fascia, hidden fasteners, "
                "composite railing kits, 6×6 column wraps, roof sheathing, ice & water "
                "shield, synthetic underlayment, drip edge, step flashing, architectural "
                "shingles, beadboard/vinyl ceiling and trim, structural hardware"
            ),
            quantity=SQFT,
            unit="sqft",
            unit_cost=MATERIALS_RATE_SQFT,
        ),
        LineItem(
            description=(
                f"Covered porch — labor ({WIDTH_FT}×{DEPTH_FT} ft, {SQFT} sq ft): "
                "layout, footings and posts, deck framing and ledger, roof framing "
                "and sheathing, roofing install, composite deck and fascia, railing, "
                "column wraps, ceiling finish, permit coordination, inspections, "
                "supervision, site protection, and cleanup"
            ),
            quantity=SQFT,
            unit="sqft",
            unit_cost=LABOR_RATE_SQFT,
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 22×8 covered porch quote")
    parser.add_argument("--client", default="Homeowner", help="Client name on quote")
    parser.add_argument("--town", default="", help="Town for scope text")
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "quotes" / "22x8-covered-porch-quote",
        help="Output path without extension",
    )
    args = parser.parse_args()

    items = porch_quote_items()
    totals = compute_quote_totals(items)
    assert abs(totals["total"] - SQFT * CUSTOMER_RATE_SQFT) < 0.01

    scope = covered_porch_scope(
        sqft=SQFT,
        width_ft=WIDTH_FT,
        depth_ft=DEPTH_FT,
        town=args.town,
    )
    timeline = default_timeline(SQFT, job_type="covered porch")
    title = f"{WIDTH_FT}×{DEPTH_FT} Covered Porch — {SQFT:g} sq ft"
    if args.town:
        suffix = args.town if "nh" in args.town.lower() else f"{args.town}, NH"
        title += f" ({suffix})"

    notes = (
        f"Questions? Call {PHONE} or email {EMAIL}. "
        "Deposit and payment schedule per signed contract. "
        "Permit fees included in materials allowance where noted by town."
    )

    html = render_quote_html(
        title=title,
        client=args.client,
        items=items,
        totals=totals,
        company=COMPANY,
        notes=notes,
        scope_of_work=scope,
        exclusions=DEFAULT_EXCLUSIONS,
        estimated_timeline=timeline,
    )

    html_path, pdf_path = render_and_save(html, f"{args.out}.html")
    print(f"Quote total: ${totals['total']:,.2f} (${CUSTOMER_RATE_SQFT:.2f}/sqft)")
    print(f"  Materials: ${items[0].total:,.2f} (${MATERIALS_RATE_SQFT:.2f}/sqft)")
    print(f"  Labor:     ${items[1].total:,.2f} (${LABOR_RATE_SQFT:.2f}/sqft)")
    print(f"HTML: {html_path}")
    if pdf_path:
        print(f"PDF:  {pdf_path}")
    else:
        print("PDF:  (install reportlab for auto-PDF, or open HTML → Print → Save as PDF)")


if __name__ == "__main__":
    main()
