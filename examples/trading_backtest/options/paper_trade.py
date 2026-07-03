#!/usr/bin/env python3
"""Paper-trade SPY 45 DTE iron condors and put credit spreads.

Usage:
    python3 paper_trade.py propose ic --symbol SPY
    python3 paper_trade.py propose pcs --symbol SPY
    python3 paper_trade.py status
    python3 paper_trade.py close <id> --reason manual
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from journal import close_position, list_open, open_position, structure_from_dict
from providers import get_provider
from structures import IronCondorParams, build_iron_condor, build_put_credit_spread, should_close_ic


def cmd_propose_ic(symbol: str, dte: int) -> None:
    prov = get_provider("yfinance")
    expiry = prov.pick_expiry(symbol, dte_target=dte)
    spot = prov.get_spot(symbol)
    chain = prov.get_chain(symbol, expiry)
    ic = build_iron_condor(symbol, spot, expiry, chain.iv_atm, params=IronCondorParams(dte_target=dte))
    pid = open_position(ic)
    mark = ic.mark(spot, chain.iv_atm)
    print(f"Opened paper IC  id={pid}")
    print(f"  {symbol} spot={spot:.2f}  expiry={expiry}  IV={chain.iv_atm:.1%}")
    print(f"  Credit: ${ic.credit_debit:.2f}  max width risk: ${IronCondorParams().wing_width * 100:.0f}")
    for leg in mark["legs"]:
        print(f"    {leg['side']:5} {leg['right']:4} {leg['strike']:.0f}  Δ={leg['delta']:.2f}")
    print(f"  Net Greeks: {json.dumps(mark['greeks'])}")


def cmd_propose_pcs(symbol: str, dte: int) -> None:
    prov = get_provider("yfinance")
    expiry = prov.pick_expiry(symbol, dte_target=dte)
    spot = prov.get_spot(symbol)
    chain = prov.get_chain(symbol, expiry)
    pcs = build_put_credit_spread(symbol, spot, expiry, chain.iv_atm)
    pid = open_position(pcs)
    mark = pcs.mark(spot, chain.iv_atm)
    print(f"Opened paper PCS  id={pid}")
    print(f"  Credit: ${pcs.credit_debit:.2f}")
    for leg in mark["legs"]:
        print(f"    {leg['side']:5} put {leg['strike']:.0f}  Δ={leg['delta']:.2f}")


def cmd_status() -> None:
    prov = get_provider("yfinance")
    positions = list_open()
    if not positions:
        print("No open paper positions.")
        return
    for pos in positions:
        s = structure_from_dict(pos["structure"])
        spot = prov.get_spot(s.underlying)
        iv = prov.get_chain(s.underlying, s.expiry).iv_atm
        mark = s.mark(spot, iv)
        close, reason = should_close_ic(s, mark) if s.name == "iron_condor" else (False, "")
        print(f"\n[{pos['id']}] {s.name} {s.underlying}  opened {pos['opened_at'][:10]}")
        print(f"  DTE={mark['dte']}  spot={spot:.2f}  P&L=${mark['pnl']:.2f} ({mark['pnl_pct_of_credit']:.0f}% of credit)")
        print(f"  Greeks: {mark['greeks']}")
        if close:
            print(f"  ** SIGNAL: close ({reason}) **")


def cmd_close(pid: str, reason: str) -> None:
    prov = get_provider("yfinance")
    for pos in list_open():
        if pos["id"] != pid:
            continue
        s = structure_from_dict(pos["structure"])
        spot = prov.get_spot(s.underlying)
        iv = prov.get_chain(s.underlying, s.expiry).iv_atm
        pnl = s.mark(spot, iv)["pnl"]
        close_position(pid, reason=reason, pnl=pnl)
        print(f"Closed {pid}  P&L=${pnl:.2f}  reason={reason}")
        return
    print(f"Position {pid} not found.")


def main() -> None:
    p = argparse.ArgumentParser(description="Paper trade SPY options structures")
    sub = p.add_subparsers(dest="cmd", required=True)

    ic = sub.add_parser("propose", help="Open new structure")
    ic_sub = ic.add_subparsers(dest="structure", required=True)
    ic_cmd = ic_sub.add_parser("ic", help="45 DTE iron condor")
    ic_cmd.add_argument("--symbol", default="SPY")
    ic_cmd.add_argument("--dte", type=int, default=45)
    pcs_cmd = ic_sub.add_parser("pcs", help="Put credit spread")
    pcs_cmd.add_argument("--symbol", default="SPY")
    pcs_cmd.add_argument("--dte", type=int, default=45)

    st = sub.add_parser("status", help="Mark open positions")
    cl = sub.add_parser("close", help="Close position")
    cl.add_argument("id")
    cl.add_argument("--reason", default="manual")

    args = p.parse_args()
    if args.cmd == "propose" and args.structure == "ic":
        cmd_propose_ic(args.symbol, args.dte)
    elif args.cmd == "propose" and args.structure == "pcs":
        cmd_propose_pcs(args.symbol, args.dte)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "close":
        cmd_close(args.id, args.reason)


if __name__ == "__main__":
    main()
