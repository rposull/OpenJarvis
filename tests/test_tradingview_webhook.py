"""Tests for TradingView alert parsing and automation helpers."""

from openjarvis.trading.tradingview_automation import (
    build_webhook_url,
    evaluate_dual_ai_decision,
    load_tradingview_account,
    market_allowed,
    normalize_action,
    parse_alert_payload,
    read_tunnel_url,
    save_tradingview_account,
    tradingview_account_payload,
)


def test_normalize_action_variants():
    assert normalize_action("buy") == "buy"
    assert normalize_action("LONG") == "buy"
    assert normalize_action("short") == "sell"
    assert normalize_action("SELL") == "sell"
    assert normalize_action("close") == "close"
    assert normalize_action("tp1") == "close"
    assert normalize_action("unknown") is None


def test_parse_oj_entry_call_json():
    body = {
        "strategy": "oj_0dte",
        "event": "entry_call",
        "symbol": "SOXL",
        "action": "buy",
        "direction": "long",
        "right": "call",
        "price": 111.5,
        "sl": 109.0,
        "tp1": 112.5,
        "tp2": 113.5,
        "tp3": 114.5,
        "entry_kind": "ORB",
    }
    parsed = parse_alert_payload(body)
    assert parsed["strategy"] == "oj_0dte"
    assert parsed["event"] == "entry_call"
    assert parsed["action"] == "buy"
    assert parsed["direction"] == "long"
    assert parsed["internal_symbol"] == "SOXL"
    assert parsed["market"] == "stock"
    assert parsed["levels"]["sl"] == 109.0


def test_parse_oj_exit_from_message_json():
    body = {
        "message": '{"strategy":"oj_0dte","event":"sl","symbol":"TQQQ","action":"close","price":88.2}',
    }
    parsed = parse_alert_payload(body)
    assert parsed["event"] == "sl"
    assert parsed["action"] == "close"
    assert parsed["internal_symbol"] == "TQQQ"


def test_parse_legacy_entry_call_text():
    body = {"message": "ENTRY CALL ORB SOXL 111.5 sl=109 tp1=112"}
    parsed = parse_alert_payload(body)
    assert parsed["event"] == "entry_call"
    assert parsed["action"] == "buy"
    assert parsed["direction"] == "long"


def test_execute_rejects_non_oj_when_locked(monkeypatch):
    from openjarvis.trading import tradingview_automation as tv

    monkeypatch.setattr(
        tv,
        "load_tradingview_config",
        lambda: {
            "only_oj_pine": True,
            "oj_strategy": "oj_0dte",
            "allowed_markets": ["stocks"],
            "trust_indicator": True,
            "execution_broker": "internal",
            "default_qty": 1,
            "oj_tp1_exit_pct": 0.5,
            "oj_tp2_exit_pct": 0.5,
        },
    )
    out = tv.execute_alert_paper_trade(
        {
            "internal_symbol": "AAPL",
            "market": "stock",
            "action": "buy",
            "strategy": None,
            "event": None,
        }
    )
    assert out["ok"] is False
    assert "only OJ" in out["error"]


def test_parse_alert_json_message():
    body = {
        "message": '{"symbol":"NASDAQ:AAPL","action":"buy","price":195.5}',
    }
    parsed = parse_alert_payload(body)
    assert parsed["tradingview_symbol"] == "NASDAQ:AAPL"
    assert parsed["internal_symbol"] == "AAPL"
    assert parsed["market"] == "stock"
    assert parsed["action"] == "buy"
    assert parsed["price"] == 195.5


def test_parse_alert_crypto_ticker():
    body = {
        "symbol": "COINBASE:DOGEUSDC",
        "action": "long",
        "price": 0.12,
    }
    parsed = parse_alert_payload(body)
    assert parsed["internal_symbol"] == "DOGE-USDC"
    assert parsed["market"] == "crypto"
    assert parsed["action"] == "buy"


def test_parse_alert_action_from_message_text():
    body = {
        "ticker": "BINANCE:BTCUSDT",
        "message": "Signal: sell BTC on breakdown",
    }
    parsed = parse_alert_payload(body)
    assert parsed["action"] == "sell"
    assert parsed["internal_symbol"] == "BTC-USDT"


def test_market_allowed():
    assert market_allowed("crypto", ["crypto", "stocks"]) is True
    assert market_allowed("stock", ["crypto", "stocks"]) is True
    assert market_allowed("stock", ["crypto"]) is False


def test_tunnel_url_file_parsing(tmp_path, monkeypatch):
    home = tmp_path / "userhome"
    oj = home / ".openjarvis"
    oj.mkdir(parents=True)
    tunnel_file = oj / "tradingview-tunnel-url.txt"
    tunnel_file.write_text(
        "provider=ngrok\n"
        "public_base=https://example.ngrok-free.dev\n"
        "webhook_url=https://example.ngrok-free.dev/api/trading/webhook/tradingview?secret=abc\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "openjarvis.trading.tradingview_automation.Path.home",
        lambda: home,
    )
    assert read_tunnel_url() == (
        "https://example.ngrok-free.dev/api/trading/webhook/tradingview?secret=abc"
    )
    assert "webhook/tradingview" in build_webhook_url("abc")


def test_tradingview_account_persist(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert load_tradingview_account(data_dir)["linked"] is False

    saved = save_tradingview_account(
        {"linked": True, "display_name": "alice", "link_method": "embedded_widget"},
        data_dir=data_dir,
    )
    assert saved["linked"] is True
    assert saved["display_name"] == "alice"
    assert saved["linked_at"] is not None

    loaded = load_tradingview_account(data_dir)
    assert loaded["linked"] is True
    assert loaded["display_name"] == "alice"

    payload = tradingview_account_payload(data_dir)
    assert payload["linked"] is True
    assert payload["oauth_available"] is False
    assert payload["login_method"] == "embedded_widget"

    cleared = save_tradingview_account({"linked": False}, data_dir=data_dir)
    assert cleared["linked"] is False
    assert cleared["display_name"] == ""


def test_dual_ai_consensus_approves(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.trading.tradingview_automation.load_tradingview_config",
        lambda: {
            "ai_enabled": True,
            "ai_mode": "consensus",
            "ai_timeout_sec": 5,
            "codex_decision_url": "https://codex.example/decide",
            "claude_decision_url": "https://claude.example/decide",
            "codex_auth_token": "",
            "claude_auth_token": "",
        },
    )
    monkeypatch.setattr(
        "openjarvis.trading.tradingview_automation._call_ai_endpoint",
        lambda url, payload, timeout_sec, token="": {
            "ok": True,
            "allow": True,
            "action": "buy",
            "reason": "pass",
        },
    )
    out = evaluate_dual_ai_decision({"internal_symbol": "QQQ", "action": "buy"})
    assert out["status"] == "approved"
    assert out["final_action"] == "buy"


def test_dual_ai_consensus_blocks_on_mismatch(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.trading.tradingview_automation.load_tradingview_config",
        lambda: {
            "ai_enabled": True,
            "ai_mode": "consensus",
            "ai_timeout_sec": 5,
            "codex_decision_url": "https://codex.example/decide",
            "claude_decision_url": "https://claude.example/decide",
        },
    )

    def _fake_call(url, payload, timeout_sec, token=""):
        return {
            "ok": True,
            "allow": True,
            "action": "buy" if "codex" in url else "sell",
            "reason": "conflict",
        }

    monkeypatch.setattr("openjarvis.trading.tradingview_automation._call_ai_endpoint", _fake_call)
    out = evaluate_dual_ai_decision({"internal_symbol": "QQQ", "action": "buy"})
    assert out["status"] == "blocked"
    assert "mismatch" in out["reason"]
