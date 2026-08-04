"""Supervisor: keeps the live paper session (and optional scanners) running."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

from trading_research.live.breakout_scanner_control import (
    breakout_scanner_status,
    ensure_breakout_scanner_stopped,
    heartbeat_stale as breakout_stale,
    start_breakout_scanner,
    stop_breakout_scanner,
    _read_pid as breakout_pid,
)
from trading_research.live.market_scout_control import (
    ensure_market_scouts_stopped,
    heartbeat_stale as scout_stale,
    market_scouts_status,
    start_market_scouts,
    stop_market_scouts,
    _read_pid as scout_pid,
)
from trading_research.live.session_control import (
    _heartbeat_stale as session_stale,
    _read_pid as session_pid,
    live_session_status,
    restart_live_session_preserve,
    start_live_session,
    stop_live_session,
)

from trading_research.live.trade_supervisors import (
    buy_supervisor_pid,
    sell_supervisor_pid,
    start_buy_supervisor,
    start_sell_supervisor,
    stop_buy_supervisor,
    stop_sell_supervisor,
)
from trading_research.live.learning_agents_control import (
    learning_agents_pid,
    learning_agents_status,
    start_learning_agents,
    stop_learning_agents,
)
from trading_research.live.chart_specialist_control import (
    chart_specialist_pid,
    chart_specialist_status,
    start_chart_specialist,
    stop_chart_specialist,
)
from trading_research.live.news_media_scout_control import (
    news_media_scout_pid,
    news_media_scout_status,
    start_news_media_scout,
    stop_news_media_scout,
)


class LiveSupervisor:
    """Monitors the live session; optional scout/breakout agents when enabled."""

    def __init__(self) -> None:
        from trading_research.jarvis_locked import get_jarvis_settings

        self.data_dir = Path(get_jarvis_settings().data_dir)
        self.stop_path = self.data_dir / "live_supervisor.stop"
        self.state_path = self.data_dir / "live_supervisor_state.json"
        self.pid_path = self.data_dir / "live_supervisor.pid"
        self._started_at = time.time()

    def _should_stop(self) -> bool:
        return self.stop_path.is_file()

    def _only_oj_pine(self) -> bool:
        from trading_research.config.market_strategy import _load_trading_toml_raw

        tv = dict(_load_trading_toml_raw().get("tradingview") or {})
        return bool(tv.get("only_oj_pine", True))

    def _scouts_enabled(self) -> bool:
        from trading_research.config.market_strategy import read_scout_strategy_toml

        if self._only_oj_pine():
            return False
        return bool(read_scout_strategy_toml().get("enabled", True))

    def _breakout_enabled(self) -> bool:
        from trading_research.config.market_strategy import (
            read_auto_strategy_toml,
            read_scout_strategy_toml,
        )

        if self._only_oj_pine():
            return False
        scout = read_scout_strategy_toml()
        auto = read_auto_strategy_toml()
        return bool(
            scout.get("enabled")
            or scout.get("auto_hot_buy")
            or auto.get("enabled")
        )

    def _trade_supervisors_enabled(self) -> bool:
        from trading_research.config.market_strategy import (
            read_auto_strategy_toml,
            read_scout_strategy_toml,
        )

        if self._only_oj_pine():
            return False
        auto = read_auto_strategy_toml()
        scout = read_scout_strategy_toml()
        return bool(
            auto.get("enabled")
            or auto.get("auto_buy")
            or auto.get("auto_sell")
            or scout.get("allow_scout_feed_orders")
            or scout.get("auto_hot_buy")
        )

    def _save_state(self, *, note: str = "") -> None:
        payload = {
            "running": True,
            "agent": "live_supervisor",
            "pid": os.getpid(),
            "started_at": self._started_at,
            "updated_at": time.time(),
            "session_pid": session_pid(),
            "breakout_pid": breakout_pid(),
            "scout_pid": scout_pid(),
            "buy_supervisor_pid": buy_supervisor_pid(),
            "sell_supervisor_pid": sell_supervisor_pid(),
            "learning_agents_pid": learning_agents_pid(),
            "chart_specialist_pid": chart_specialist_pid(),
            "news_media_scout_pid": news_media_scout_pid(),
            "note": note,
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _ensure_session(self) -> str:
        pid = session_pid()
        if pid is not None and not session_stale(max_age_sec=180.0):
            return f"session ok (PID {pid})"
        if pid is not None:
            print(f"[SUPERVISOR] stale session PID {pid} — restarting", flush=True)
            restart_live_session_preserve()
        msg = start_live_session()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "session restarted"

    def _ensure_breakout_scanner(self) -> str:
        if not self._breakout_enabled():
            if breakout_pid() is not None:
                print("[SUPERVISOR] breakout scanner disabled — stopping", flush=True)
                ensure_breakout_scanner_stopped()
            return "breakout scanner disabled"
        pid = breakout_pid()
        if pid is not None and not breakout_stale():
            return f"breakout scanner ok (PID {pid})"
        if pid is not None:
            print(f"[SUPERVISOR] stale breakout scanner PID {pid} — restarting", flush=True)
            ensure_breakout_scanner_stopped()
        msg = start_breakout_scanner()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "breakout scanner restarted"

    def _ensure_market_scouts(self) -> str:
        from trading_research.live.market_scout_control import scout_heartbeat_max_sec

        if not self._scouts_enabled():
            if scout_pid() is not None:
                print("[SUPERVISOR] market scouts disabled — stopping", flush=True)
                ensure_market_scouts_stopped()
            return "market scouts disabled"
        pid = scout_pid()
        max_age = scout_heartbeat_max_sec()
        if pid is not None and not scout_stale(max_age_sec=max_age):
            return f"market scouts ok (PID {pid})"
        if pid is not None:
            print(f"[SUPERVISOR] stale market scouts PID {pid} — restarting", flush=True)
            ensure_market_scouts_stopped()
        msg = start_market_scouts()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "market scouts restarted"

    def _sync_trade_ledger(self) -> None:
        from trading_research.live.trade_ledger_sync import sync_trade_ledger_file

        if sync_trade_ledger_file():
            print("[SUPERVISOR] synced live_trade_ledger.json from snapshot", flush=True)

    def _maybe_rotate_logs(self) -> None:
        from trading_research.jarvis_locked import get_jarvis_settings
        from trading_research.storage.log_rotation import rotate_all_logs

        result = rotate_all_logs(get_jarvis_settings().logs_dir)
        if not result.get("count"):
            return
        print(
            f"[SUPERVISOR] rotated logs: "
            f"jsonl={result.get('jsonl_rotated')} text={result.get('text_rotated')}",
            flush=True,
        )

    def _maybe_prune_candles(self, *, note: str = "") -> None:
        from trading_research.config.market_strategy import read_chart_strategy_toml
        from trading_research.live.chart_history import maybe_prune_candle_storage

        chart_cfg = read_chart_strategy_toml()
        result = maybe_prune_candle_storage(self.data_dir, chart_cfg=chart_cfg)
        if not result or not result.get("files_removed"):
            return
        mb = round(float(result.get("bytes_freed") or 0) / (1024 * 1024), 2)
        print(
            f"[SUPERVISOR] pruned {result['files_removed']} candle file(s) "
            f"({mb} MB freed, disk {result.get('disk_free_gb_after')} GB free) "
            f"— {note}",
            flush=True,
        )

    def _ensure_buy_supervisor(self) -> str:
        from trading_research.live.trade_supervisors import _heartbeat_stale

        if not self._trade_supervisors_enabled():
            if buy_supervisor_pid() is not None:
                print("[SUPERVISOR] buy supervisor disabled — stopping", flush=True)
                stop_buy_supervisor()
            return "buy supervisor disabled"
        pid = buy_supervisor_pid()
        state_path = self.data_dir / "buy_supervisor_state.json"
        if pid is not None and not _heartbeat_stale(state_path):
            return f"buy supervisor ok (PID {pid})"
        if pid is not None:
            print(f"[SUPERVISOR] stale buy supervisor PID {pid} — restarting", flush=True)
        msg = start_buy_supervisor()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "buy supervisor restarted"

    def _ensure_chart_specialist(self) -> str:
        from trading_research.config.market_strategy import read_chart_specialist_toml

        if not read_chart_specialist_toml().get("enabled", True):
            return "chart specialist disabled"
        st = chart_specialist_status()
        pid = st.get("pid")
        if pid and st.get("running"):
            updated = float(st.get("updated_at") or 0)
            if updated and (time.time() - updated) < 900:
                return f"chart specialist ok (PID {pid})"
        if pid:
            stop_chart_specialist()
        msg = start_chart_specialist()
        print(f"[SUPERVISOR] {msg}", flush=True)
        return "chart specialist restarted"

    def _ensure_news_media_scout(self) -> str:
        from trading_research.config.market_strategy import read_news_media_scout_toml

        if not read_news_media_scout_toml().get("enabled", True):
            return "news media scout disabled"
        st = news_media_scout_status()
        pid = st.get("pid")
        if pid and st.get("running"):
            updated = float(st.get("updated_at") or 0)
            if updated and (time.time() - updated) < 900:
                return f"news media scout ok (PID {pid})"
        if pid:
            stop_news_media_scout()
        msg = start_news_media_scout()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "news media scout restarted"

    def _ensure_qlib_signals(self) -> str:
        from trading_research.config.market_strategy import read_qlib_signals_toml
        from trading_research.scripts.run_qlib_signals import run_qlib_signal_job

        cfg = read_qlib_signals_toml()
        if not cfg.get("enabled", True):
            return "qlib signals disabled"
        try:
            result = run_qlib_signal_job(data_dir=self.data_dir, force=False)
        except Exception as exc:
            return f"qlib signals error: {exc}"
        if result.get("skipped"):
            return "qlib signals fresh"
        if result.get("ok"):
            bias = result.get("global_bias") or "?"
            return f"qlib signals refreshed (bias={bias})"
        return f"qlib signals failed: {result.get('error', '?')}"

    def _ensure_kronos_signals(self) -> str:
        from trading_research.config.market_strategy import read_kronos_signals_toml
        from trading_research.scripts.run_kronos_signals import run_kronos_signal_job

        cfg = read_kronos_signals_toml()
        if not cfg.get("enabled", True):
            return "kronos signals disabled"
        try:
            result = run_kronos_signal_job(data_dir=self.data_dir, force=False)
        except Exception as exc:
            return f"kronos signals error: {exc}"
        if result.get("skipped"):
            return "kronos signals fresh"
        if result.get("ok"):
            bias = result.get("global_bias") or "?"
            return f"kronos signals refreshed (bias={bias})"
        return f"kronos signals failed: {result.get('error', '?')}"

    def _ensure_learning_agents(self) -> str:
        from trading_research.config.market_strategy import (
            read_structure_learner_toml,
            read_win_rate_optimizer_toml,
        )

        struct_on = read_structure_learner_toml().get("enabled", True)
        wr_on = read_win_rate_optimizer_toml().get("enabled", True)
        if not struct_on and not wr_on:
            return "learning agents disabled"
        st = learning_agents_status()
        pid = st.get("pid")
        if pid and st.get("running"):
            updated = float(st.get("updated_at") or 0)
            if updated and (time.time() - updated) < 900:
                return f"learning agents ok (PID {pid})"
        if pid:
            print(f"[SUPERVISOR] stale learning agents PID {pid} — restarting", flush=True)
            stop_learning_agents()
        msg = start_learning_agents()
        print(f"[SUPERVISOR] {msg}", flush=True)
        return "learning agents restarted"

    def _ensure_sell_supervisor(self) -> str:
        from trading_research.live.trade_supervisors import _heartbeat_stale

        if not self._trade_supervisors_enabled():
            if sell_supervisor_pid() is not None:
                print("[SUPERVISOR] sell supervisor disabled — stopping", flush=True)
                stop_sell_supervisor()
            return "sell supervisor disabled"
        pid = sell_supervisor_pid()
        state_path = self.data_dir / "sell_supervisor_state.json"
        if pid is not None and not _heartbeat_stale(state_path):
            return f"sell supervisor ok (PID {pid})"
        if pid is not None:
            print(f"[SUPERVISOR] stale sell supervisor PID {pid} — restarting", flush=True)
        msg = start_sell_supervisor()
        print(f"[SUPERVISOR] {msg.splitlines()[0]}", flush=True)
        return "sell supervisor restarted"

    def run(self, *, check_sec: float = 90.0) -> int:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.stop_path.unlink(missing_ok=True)
        pid = os.getpid()
        self.pid_path.write_text(str(pid), encoding="utf-8")

        mode = "OJ 0DTE Pine only" if self._only_oj_pine() else "scanners optional"
        banner = (
            "=== LIVE SUPERVISOR ===\n"
            f"  Mode: {mode}\n"
            "  Manages: session + optional breakout/scouts/BUY/SELL + chart/news/learning\n"
            f"  Check interval: {check_sec:.0f}s\n"
        )
        print(banner, flush=True)

        self._ensure_session()
        self._ensure_breakout_scanner()
        self._ensure_market_scouts()
        self._ensure_buy_supervisor()
        self._ensure_sell_supervisor()
        self._ensure_learning_agents()
        self._ensure_chart_specialist()
        self._ensure_news_media_scout()
        qlib_note = self._ensure_qlib_signals()
        print(f"[SUPERVISOR] {qlib_note}", flush=True)
        kronos_note = self._ensure_kronos_signals()
        print(f"[SUPERVISOR] {kronos_note}", flush=True)
        self._maybe_rotate_logs()
        self._maybe_prune_candles(note="startup")
        self._sync_trade_ledger()
        self._save_state(note="started all agents")

        exit_code = 0
        _prune_every = 10
        _loop = 0
        try:
            while not self._should_stop():
                try:
                    s_note = self._ensure_session()
                    b_note = self._ensure_breakout_scanner()
                    m_note = self._ensure_market_scouts()
                    buy_note = self._ensure_buy_supervisor()
                    sell_note = self._ensure_sell_supervisor()
                    learn_note = self._ensure_learning_agents()
                    chart_note = self._ensure_chart_specialist()
                    news_note = self._ensure_news_media_scout()
                    qlib_note = self._ensure_qlib_signals()
                    kronos_note = self._ensure_kronos_signals()
                    _loop += 1
                    if _loop % _prune_every == 0:
                        self._maybe_rotate_logs()
                        self._maybe_prune_candles(note=f"loop {_loop}")
                        self._sync_trade_ledger()
                    self._save_state(
                        note=f"{s_note}; {b_note}; {m_note}; {buy_note}; {sell_note}; {learn_note}; {chart_note}; {news_note}; {qlib_note}; {kronos_note}"
                    )
                except Exception as exc:
                    print(f"[SUPERVISOR-ERROR] {exc}\n{traceback.format_exc()}", flush=True)
                time.sleep(check_sec)
        except Exception as exc:
            exit_code = 1
            print(f"[SUPERVISOR-FATAL] {exc}", flush=True)
        finally:
            self.state_path.write_text(
                json.dumps(
                    {
                        "running": False,
                        "agent": "live_supervisor",
                        "updated_at": time.time(),
                        "note": "stopped",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.pid_path.unlink(missing_ok=True)
            self.stop_path.unlink(missing_ok=True)
        return exit_code


def start_live_supervisor(*, check_sec: float = 90.0) -> str:
    """Spawn supervisor in background (starts live session; optional scanners)."""
    data_dir = Path(__file__).resolve().parents[1] / "data"
    from trading_research.jarvis_locked import get_jarvis_settings

    data_dir = Path(get_jarvis_settings().data_dir)
    pid_path = data_dir / "live_supervisor.pid"
    stop_path = data_dir / "live_supervisor.stop"

    if pid_path.is_file():
        try:
            old = int(pid_path.read_text(encoding="utf-8").strip())
            if sys.platform == "win32":
                r = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {old}", "/NH"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                alive = str(old) in (r.stdout or "")
            else:
                try:
                    os.kill(old, 0)
                    alive = True
                except OSError:
                    alive = False
            if alive:
                return f"Live supervisor already running (PID {old})."
        except ValueError:
            pid_path.unlink(missing_ok=True)

    log_path = Path(get_jarvis_settings().logs_dir) / "live_supervisor.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("JARVIS_TRADING_LOCKED", "1")
    env.setdefault("TR_DATA_DIR", str(data_dir))
    env.setdefault("TR_LOGS_DIR", get_jarvis_settings().logs_dir)
    env.setdefault("TR_SUPERVISOR_CHECK_SEC", str(check_sec))
    env.setdefault("PYTHONUNBUFFERED", "1")
    repo = str(Path(__file__).resolve().parents[2])
    prefix = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = repo if not prefix else f"{repo}{os.pathsep}{prefix}"

    stop_path.unlink(missing_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    cmd = [sys.executable, "-u", "-m", "trading_research.live.live_supervisor"]
    popen_kw: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
        "env": env,
        "cwd": repo,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        popen_kw["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kw)
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    for _ in range(120):
        time.sleep(1)
        if proc.poll() is not None:
            return f"Live supervisor failed to start (exit {proc.returncode})."
        if session_pid():
            break

    return (
        f"Live supervisor started (PID {proc.pid}).\n"
        f"  Session PID: {session_pid() or 'starting…'}\n"
        f"  Breakout scanner PID: {breakout_pid() or 'off'}\n"
        f"  Market scouts PID: {scout_pid() or 'off'}\n"
        f"Log: {log_path}\n"
        "Enabled agents will auto-restart if they crash."
    )


def stop_live_supervisor(*, stop_children: bool = False) -> str:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    from trading_research.jarvis_locked import get_jarvis_settings

    data_dir = Path(get_jarvis_settings().data_dir)
    stop_path = data_dir / "live_supervisor.stop"
    pid_path = data_dir / "live_supervisor.pid"

    stop_path.write_text("stop", encoding="utf-8")
    for _ in range(30):
        time.sleep(1)
        if not pid_path.is_file():
            break
    else:
        if pid_path.is_file():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
                else:
                    os.kill(pid, 9)
            except (ValueError, OSError):
                pass
            pid_path.unlink(missing_ok=True)

    msg = "Live supervisor stopped."
    if stop_children:
        from trading_research.live.trade_supervisors import (
            stop_buy_supervisor,
            stop_sell_supervisor,
        )

        msg += "\n" + stop_live_session()
        msg += "\n" + stop_breakout_scanner()
        msg += "\n" + stop_market_scouts()
        msg += "\n" + stop_buy_supervisor()
        msg += "\n" + stop_sell_supervisor()
    stop_path.unlink(missing_ok=True)
    return msg


def live_supervisor_status() -> str:
    from trading_research.live.trade_supervisors import trade_supervisors_status

    parts = [
        live_session_status(),
        "",
        breakout_scanner_status(),
        "",
        market_scouts_status(),
        "",
        trade_supervisors_status(),
    ]
    return "\n".join(parts)


def main() -> int:
    check = float(os.environ.get("TR_SUPERVISOR_CHECK_SEC", "90"))
    sup = LiveSupervisor()

    def _sig(_signum, _frame):
        sup.stop_path.write_text("stop", encoding="utf-8")

    signal.signal(signal.SIGTERM, _sig)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _sig)
    return sup.run(check_sec=check)


if __name__ == "__main__":
    raise SystemExit(main())
