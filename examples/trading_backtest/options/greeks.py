"""Black-Scholes pricing and Greeks (European options)."""

from __future__ import annotations

import math
from dataclasses import dataclass

SQRT_2PI = math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


@dataclass(frozen=True)
class OptionQuote:
    spot: float
    strike: float
    t_years: float
    rate: float
    iv: float
    is_call: bool

    def price(self) -> float:
        return bs_price(
            self.spot, self.strike, self.t_years, self.rate, self.iv, self.is_call
        )

    def greeks(self) -> dict[str, float]:
        return bs_greeks(
            self.spot, self.strike, self.t_years, self.rate, self.iv, self.is_call
        )


def _d1d2(s: float, k: float, t: float, r: float, sigma: float) -> tuple[float, float]:
    if t <= 0 or sigma <= 0 or s <= 0 or k <= 0:
        return 0.0, 0.0
    d1 = (math.log(s / k) + (r + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return d1, d2


def bs_price(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> float:
    if t <= 0:
        return max(0.0, s - k) if is_call else max(0.0, k - s)
    if sigma <= 0:
        fwd = s * math.exp(r * t)
        return max(0.0, fwd - k) * math.exp(-r * t) if is_call else max(0.0, k - fwd) * math.exp(
            -r * t
        )
    d1, d2 = _d1d2(s, k, t, r, sigma)
    if is_call:
        return s * norm_cdf(d1) - k * math.exp(-r * t) * norm_cdf(d2)
    return k * math.exp(-r * t) * norm_cdf(-d2) - s * norm_cdf(-d1)


def bs_greeks(
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> dict[str, float]:
    if t <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1, d2 = _d1d2(s, k, t, r, sigma)
    pdf = norm_pdf(d1)
    delta = norm_cdf(d1) if is_call else norm_cdf(d1) - 1
    gamma = pdf / (s * sigma * math.sqrt(t))
    vega = s * pdf * math.sqrt(t) / 100
    if is_call:
        theta = (
            -s * pdf * sigma / (2 * math.sqrt(t))
            - r * k * math.exp(-r * t) * norm_cdf(d2)
        ) / 365
    else:
        theta = (
            -s * pdf * sigma / (2 * math.sqrt(t))
            + r * k * math.exp(-r * t) * norm_cdf(-d2)
        ) / 365
    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
        "vega": float(vega),
    }


def strike_for_delta(
    spot: float,
    t: float,
    r: float,
    iv: float,
    target_delta: float,
    is_call: bool,
) -> float:
    """Binary search strike for target absolute delta."""
    lo, hi = spot * 0.5, spot * 1.5
    target = abs(target_delta)
    for _ in range(80):
        mid = (lo + hi) / 2
        d = abs(bs_greeks(spot, mid, t, r, iv, is_call)["delta"])
        if is_call:
            if d > target:
                lo = mid
            else:
                hi = mid
        else:
            if d > target:
                hi = mid
            else:
                lo = mid
    return round((lo + hi) / 2, 0)


def iv_from_price(
    market_price: float,
    spot: float,
    strike: float,
    t: float,
    r: float,
    is_call: bool,
    tol: float = 1e-5,
) -> float:
    """Solve implied vol via bisection."""
    lo, hi = 0.01, 3.0
    for _ in range(100):
        mid = (lo + hi) / 2
        p = bs_price(spot, strike, t, r, mid, is_call)
        if p > market_price:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2
