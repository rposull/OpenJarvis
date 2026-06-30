#!/usr/bin/env python3
"""Seed construction catalog from live_prices.json (all trades + materials).

Same as::

    uv run python examples/southern_nh_gc/refresh_live_pricing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from refresh_live_pricing import main

if __name__ == "__main__":
    main()
