import json
from pathlib import Path


def load_state(path="state.json"):
    p = Path(path)
    if not p.exists():
        return {"version": 1, "sources": {}}
    return json.loads(p.read_text())


def save_state(state, path="state.json"):
    Path(path).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
