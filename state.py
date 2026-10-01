"""État persistant : pour chaque mail vu, le ticket Jira associé et le dernier statut appliqué.

{ "<message-id>": {"issue_key": "KAN-12" | null, "status": "Planifier" | null} }
"""
import json
import os
from pathlib import Path

STATE_FILE = Path(os.getenv("STATE_FILE") or Path(__file__).with_name("processed.json"))


def load() -> dict:
    if not STATE_FILE.exists() or not STATE_FILE.read_text().strip():
        return {}
    raw = json.loads(STATE_FILE.read_text())
    if isinstance(raw, list):  # ancien format : simple liste d'identifiants
        return {mid: {"issue_key": None, "status": None} for mid in raw}
    return raw


def save(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(STATE_FILE)
