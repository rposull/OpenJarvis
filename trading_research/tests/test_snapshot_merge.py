"""Regression: live snapshot save must not wipe external webhook fills."""

from __future__ import annotations

from pathlib import Path

from trading_research.config.settings import Settings
from trading_research.core_types import LONG, PaperTrade
from trading_research.execution.paper_broker import PaperBroker
from trading_research.learning.session_learner import SessionLearner
from trading_research.live.session_persistence import load_snapshot, save_snapshot


class _Stub:
    def __init__(self, settings, broker):
        self.s = settings
        self.broker = broker
        self.session = SessionLearner(settings)
        self._started_at = 1.0
        self._bootstrapped = True
        self.last_bar_ts = {}


def _settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.data_dir = str(tmp_path / "data")
    s.logs_dir = str(tmp_path / "logs")
    Path(s.data_dir).mkdir(parents=True, exist_ok=True)
    Path(s.logs_dir).mkdir(parents=True, exist_ok=True)
    return s


def test_save_snapshot_merges_orphan_disk_positions(tmp_path):
    s = _settings(tmp_path)

    disk_broker = PaperBroker(s, starting_equity=100000)
    orphan = PaperTrade(
        id="orphan-oj-1",
        symbol="SOXL",
        market="stock",
        side=LONG,
        kind="option",
        entry_price=1.0,
        qty=1,
        stop=0.5,
        tp1=1.5,
        tp2=2.0,
        status="open",
        meta={"entry_source": "oj_0dte_pine", "qty_remaining": 1},
    )
    disk_broker.positions[orphan.id] = orphan
    disk_broker.state.open_trades = 1
    save_snapshot(_Stub(s, disk_broker))

    live_broker = PaperBroker(s, starting_equity=100000)
    save_snapshot(_Stub(s, live_broker))

    snap = load_snapshot(s)
    assert snap is not None
    ids = {p["id"] for p in snap.get("positions") or []}
    assert "orphan-oj-1" in ids
    assert live_broker.positions.get("orphan-oj-1") is not None
