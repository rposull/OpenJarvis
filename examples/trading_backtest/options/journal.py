"""Paper trade journal (JSON file)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from structures import OptionStructure

DEFAULT_JOURNAL = Path(__file__).resolve().parent / "paper_journal.json"


def _load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"positions": [], "closed": []}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def open_position(structure: OptionStructure, path: Path = DEFAULT_JOURNAL) -> str:
    data = _load(path)
    pid = str(uuid.uuid4())[:8]
    entry = {
        "id": pid,
        "status": "open",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "structure": structure.to_dict(),
    }
    data["positions"].append(entry)
    _save(path, data)
    return pid


def list_open(path: Path = DEFAULT_JOURNAL) -> list[dict]:
    return _load(path)["positions"]


def close_position(
    pid: str,
    *,
    reason: str,
    pnl: float,
    path: Path = DEFAULT_JOURNAL,
) -> bool:
    data = _load(path)
    for i, pos in enumerate(data["positions"]):
        if pos["id"] == pid:
            pos["status"] = "closed"
            pos["closed_at"] = datetime.now(timezone.utc).isoformat()
            pos["close_reason"] = reason
            pos["realized_pnl"] = pnl
            data["closed"].append(pos)
            data["positions"].pop(i)
            _save(path, data)
            return True
    return False


def structure_from_dict(d: dict) -> OptionStructure:
    from structures import Leg, OptionStructure

    legs = [Leg(**lg) for lg in d["legs"]]
    return OptionStructure(
        name=d["name"],
        underlying=d["underlying"],
        expiry=date.fromisoformat(d["expiry"]),
        legs=legs,
        opened=date.fromisoformat(d["opened"]) if d.get("opened") else None,
        credit_debit=d.get("credit_debit", 0),
        notes=d.get("notes", ""),
    )
