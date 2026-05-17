from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Dict, Any

HISTORY_PATH = "auction_history.jsonl"


def save_listing(data: Dict[str, Any], path: str = HISTORY_PATH) -> None:
    record = {"created_at": datetime.now().isoformat(timespec="seconds"), **data}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(path: str = HISTORY_PATH):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
