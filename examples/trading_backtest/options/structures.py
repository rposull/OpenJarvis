"""Option structures: iron condor, put credit spread."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Literal

from greeks import OptionQuote, bs_greeks, bs_price, strike_for_delta

LegSide = Literal["long", "short"]
OptionRight = Literal["call", "put"]


@dataclass
class Leg:
    right: OptionRight
    strike: float
    side: LegSide
    qty: int = 1

    def signed_qty(self) -> int:
        return self.qty if self.side == "long" else -self.qty


@dataclass
class OptionStructure:
    name: str
    underlying: str
    expiry: date
    legs: list[Leg]
    opened: date | None = None
    credit_debit: float = 0.0  # positive = net credit received
    notes: str = ""

    def dte(self, as_of: date | None = None) -> int:
        today = as_of or date.today()
        return (self.expiry - today).days

    def mark(
        self,
        spot: float,
        iv: float,
        *,
        rate: float = 0.045,
        as_of: date | None = None,
    ) -> dict:
        today = as_of or date.today()
        t = max(self.dte(today), 0) / 365.0
        leg_marks = []
        total = 0.0
        greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        for leg in self.legs:
            q = OptionQuote(spot, leg.strike, t, rate, iv, leg.right == "call")
            px = q.price()
            signed = px * leg.signed_qty() * 100
            total += signed
            g = q.greeks()
            mult = leg.signed_qty() * 100
            for k in greeks:
                greeks[k] += g[k] * mult
            leg_marks.append(
                {
                    "right": leg.right,
                    "strike": leg.strike,
                    "side": leg.side,
                    "mark": round(px, 4),
                    "delta": round(g["delta"], 4),
                }
            )
        # P&L for short premium structures: credit received + current liability
        pnl = self.credit_debit + total if self.credit_debit else total
        return {
            "spot": spot,
            "iv": iv,
            "dte": self.dte(today),
            "net_mark": round(total, 2),
            "pnl": round(pnl, 2),
            "pnl_pct_of_credit": round(pnl / self.credit_debit * 100, 1)
            if self.credit_debit
            else 0.0,
            "greeks": {k: round(v, 3) for k, v in greeks.items()},
            "legs": leg_marks,
        }

    def to_dict(self) -> dict:
        d = asdict(self)
        d["expiry"] = self.expiry.isoformat()
        d["opened"] = self.opened.isoformat() if self.opened else None
        return d


@dataclass
class IronCondorParams:
    target_delta: float = 0.16
    wing_width: float = 5.0
    dte_target: int = 45
    dte_exit: int = 21
    profit_take_pct: float = 50.0
    max_loss_mult: float = 2.0  # exit if loss = 2x credit


def build_iron_condor(
    underlying: str,
    spot: float,
    expiry: date,
    iv: float,
    *,
    params: IronCondorParams | None = None,
    rate: float = 0.045,
) -> OptionStructure:
    p = params or IronCondorParams()
    t = max((expiry - date.today()).days, 1) / 365.0
    short_put = strike_for_delta(spot, t, rate, iv, p.target_delta, is_call=False)
    short_call = strike_for_delta(spot, t, rate, iv, p.target_delta, is_call=True)
    long_put = short_put - p.wing_width
    long_call = short_call + p.wing_width

    legs = [
        Leg("put", long_put, "long"),
        Leg("put", short_put, "short"),
        Leg("call", short_call, "short"),
        Leg("call", long_call, "long"),
    ]
    # Net credit (per share); multiply by 100 for contract
    credit = 0.0
    for leg in legs:
        px = bs_price(spot, leg.strike, t, rate, iv, leg.right == "call")
        credit -= px * leg.signed_qty()
    return OptionStructure(
        name="iron_condor",
        underlying=underlying,
        expiry=expiry,
        legs=legs,
        opened=date.today(),
        credit_debit=round(credit * 100, 2),
        notes=f"{p.dte_target}DTE IC ~{p.target_delta}Δ wings ${p.wing_width}",
    )


def build_put_credit_spread(
    underlying: str,
    spot: float,
    expiry: date,
    iv: float,
    *,
    target_delta: float = 0.20,
    width: float = 5.0,
    rate: float = 0.045,
) -> OptionStructure:
    t = max((expiry - date.today()).days, 1) / 365.0
    short_put = strike_for_delta(spot, t, rate, iv, target_delta, is_call=False)
    long_put = short_put - width
    legs = [Leg("put", long_put, "long"), Leg("put", short_put, "short")]
    credit = 0.0
    for leg in legs:
        px = bs_price(spot, leg.strike, t, rate, iv, False)
        credit -= px * leg.signed_qty()
    return OptionStructure(
        name="put_credit_spread",
        underlying=underlying,
        expiry=expiry,
        legs=legs,
        opened=date.today(),
        credit_debit=round(credit * 100, 2),
        notes=f"PCS ~{target_delta}Δ width ${width}",
    )


def should_close_ic(
    structure: OptionStructure,
    mark: dict,
    params: IronCondorParams | None = None,
) -> tuple[bool, str]:
    p = params or IronCondorParams()
    dte = mark["dte"]
    pnl_pct = mark.get("pnl_pct_of_credit", 0)
    credit = structure.credit_debit

    if dte <= p.dte_exit:
        return True, f"time_exit_{dte}dte"
    if credit > 0 and pnl_pct >= p.profit_take_pct:
        return True, f"profit_take_{pnl_pct:.0f}pct"
    if credit > 0 and mark["pnl"] <= -credit * p.max_loss_mult:
        return True, "max_loss_stop"
    return False, ""
