"""Default scope-of-work text for customer quotes — customize per job.

Use in quote_create ``scope_of_work`` / ``exclusions`` / ``estimated_timeline``.
Pricing stays one all-in line for decks; garage and addition use materials + labor lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shop_pricing import REFERENCE_CREW_DAYS, SQFT_PER_CREW_DAY


def _days_for(sqft: float) -> int:
    return max(1, round(sqft / SQFT_PER_CREW_DAY))


def deck_scope(
    *,
    sqft: float,
    town: str = "",
    decking: str = "pressure-treated or composite per client selection",
    railing: str = "code-compliant wood or aluminum railing",
    stairs: bool = False,
    attached: bool = True,
) -> str:
    """Detailed deck scope for a customer quote."""
    days = _days_for(sqft)
    loc = f" in {town}" if town else ""
    stair_line = (
        "- Install deck stairs with stringers, treads, and guards per code\n"
        if stairs
        else ""
    )
    attach = (
        "Attach ledger to existing structure with flashing and waterproofing "
        "at the house connection"
        if attached
        else "Build freestanding deck with independent footings and bracing"
    )
    return f"""Project overview:
- Furnish all labor, materials, and supervision to build a {sqft:g} sq ft deck{loc}
- Work performed in accordance with applicable NH building codes and local amendments

Site work and layout:
- Locate underground utilities before digging (Dig Safe / 811)
- Layout deck footprint, establish elevations, and protect adjacent landscaping

Permits and inspections:
- Assist homeowner with permit application and required drawings
- Schedule and meet inspector for footing, framing, and final inspections as required

Foundation:
- Install concrete footings or sono tubes sized per frost depth and load requirements
- Set posts or piers plumb and to grade

Framing:
- {attach}
- Install pressure-treated joists, beams, and blocking per engineered span tables
- Install approved metal hardware and fasteners throughout

Decking and finishes:
- Install {decking} decking with uniform gapping and secure fastening
- Install {railing} on open sides
{stair_line}- Trim, fascia, and detail work at visible edges

Cleanup and closeout:
- Daily jobsite cleanup; haul off construction debris
- Final walkthrough with homeowner
- Provide care instructions for decking and finishes

Estimated timeline:
- Approximately {days} working days on site, weather permitting"""


def garage_scope(
    *,
    sqft: float,
    town: str = "",
    dimensions: str = "",
    slab: bool = True,
) -> str:
    days = max(_days_for(sqft), 14)
    size = dimensions or f"{sqft:g} sq ft footprint"
    loc = f" in {town}" if town else ""
    slab_text = (
        "- Excavate, compact base, install gravel, and pour 4\" concrete slab with control joints\n"
        if slab
        else ""
    )
    return f"""Project overview:
- Furnish labor and materials to construct a {size} detached garage{loc}
- Work per NH state building code and local zoning setbacks

Site and foundation:
{slab_text}- Set anchor bolts and sill plates per code

Framing and structure:
- Frame walls with pressure-treated bottom plates and specified stud spacing
- Install headers, lintels, and shear nailing as required
- Install roof trusses or stick-framed roof with sheathing and approved underlayment
- Install garage door opening with proper header sizing

Exterior:
- Install housewrap, windows if included in scope, and exterior siding or sheathing wrap
- Install soffit, fascia, and trim

Garage door and openings:
- Rough opening prepared for standard overhead door (door unit quoted separately unless noted)
- Install man door or windows only if specified in this estimate

Cleanup:
- Jobsite cleanup and debris removal
- Final walkthrough with homeowner

Estimated timeline:
- Approximately {days} working days on site, weather permitting"""


def addition_scope(
    *,
    sqft: float,
    town: str = "",
    stories: str = "single-story",
) -> str:
    days = max(_days_for(sqft), 21)
    loc = f" in {town}" if town else ""
    return f"""Project overview:
- Furnish labor and materials for a {stories} home addition of approximately {sqft:g} sq ft{loc}
- Integrate new construction with existing structure per code

Preconstruction:
- Protect existing home interior/exterior at tie-in areas
- Layout addition footprint and verify setbacks

Foundation and framing:
- Excavate and pour foundation or frost walls per engineered design
- Frame floor system, walls, and roof with proper tie-in to existing structure
- Install roof-to-wall flashing and weather barrier at marriage line

Building envelope:
- Install sheathing, housewrap, windows, and exterior doors as specified
- Roof shingles tied into existing roof with step flashing and ice/water shield at valleys/eaves

Rough openings:
- Coordinate rough openings for HVAC, plumbing, and electrical with licensed trades (by others unless noted)

Interior prep (shell):
- Insulation and air sealing at exterior walls and roof as specified
- Drywall hang, tape, and sand ready for paint (finish paint by others unless noted)

Permits and inspections:
- Permit support and required inspections through framing, insulation, and final

Cleanup:
- Daily cleanup; dumpster service included
- Final walkthrough

Estimated timeline:
- Approximately {days} working days on site, weather and trade coordination permitting"""


DEFAULT_EXCLUSIONS = """- Electrical wiring, panels, and fixtures (by licensed electrician unless added)
- Plumbing, gas lines, and HVAC (by licensed trades unless added)
- Interior paint, stain, and floor finishes unless explicitly listed
- Landscaping, irrigation repair, and hardscape beyond disturbed areas
- Engineering or architectural stamp if required by town (quoted separately)
- Unforeseen site conditions (rock, ledge, poor soils) — change order if encountered"""


def default_timeline(sqft: float, job_type: str = "deck") -> str:
    days = _days_for(sqft)
    if job_type == "garage":
        days = max(days, 14)
    elif job_type == "addition":
        days = max(days, 21)
    elif job_type in ("covered porch", "porch"):
        days = max(days, 12)
    return (
        f"Approximately {days} working days on site ({REFERENCE_CREW_DAYS} days "
        f"reference for a 144 sq ft deck). Weather, permits, and material "
        f"lead times may adjust start/finish."
    )


def covered_porch_scope(
    *,
    sqft: float,
    width_ft: float = 22,
    depth_ft: float = 8,
    town: str = "",
    decking: str = "composite decking with hidden fasteners",
    railing: str = "composite railing system",
    footings_allowance: float = 2200.0,
) -> str:
    """Detailed scope for a covered porch — deck, roof, ceiling, columns."""
    days = max(_days_for(sqft), 12)
    loc = f" in {town}" if town else ""
    footprint = f"{width_ft:g} ft × {depth_ft:g} ft ({sqft:g} sq ft)"
    return f"""Project overview:
- Furnish all labor, materials, and supervision to build a {footprint} covered porch{loc}
- Work performed per applicable NH building codes and local amendments

Permits and inspections:
- Assist with building permit application and required drawings
- Schedule inspections for footings, framing, roofing, and final as required by town

Foundation and posts:
- Install concrete footings below local frost depth for porch posts (allowance {footings_allowance:,.0f})
- Set (3) pressure-treated 6×6 posts plumb and to elevation
- Install post bases, anchors, and approved hardware

Deck structure and framing:
- Attach ledger to existing structure with flashing and waterproofing at house connection
- Install pressure-treated 2×10 beams, rim boards, blocking, and joists per span requirements
- Install approved joist hangers, hurricane ties, and structural fasteners (not shown on material takeoff)

Roof structure:
- Frame roof with 2×10 headers, rafters, and 2×6 ceiling ties per plan
- Install 1/2\" roof sheathing and structural connections at house tie-in

Roofing:
- Install ice and water shield at eaves and critical transitions
- Install synthetic underlayment over sheathing
- Install drip edge, step flashing at house wall, and architectural shingles
- Tie roof drainage into existing gutters only if specified in writing

Decking and rail:
- Install {decking} on framed deck surface
- Install composite fascia at exposed edges
- Install {railing} at open sides per code (guard height and spacing)

Columns and ceiling:
- Install 6×6 column wrap kits at structural posts
- Install beadboard or vinyl ceiling finish with J-channel and F-channel trim

Cleanup and closeout:
- Daily jobsite cleanup; haul off construction debris
- Final walkthrough with homeowner
- Provide care instructions for composite and roof finishes

Estimated timeline:
- Approximately {days} working days on site, weather permitting"""
