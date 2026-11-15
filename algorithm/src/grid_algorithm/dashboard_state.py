import json
import sqlite3
from pathlib import Path


def read_events(path, limit=12000):
    if not Path(path).is_file(): return []
    with sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT t_s,utc,kind,payload FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(t_s=t, utc=utc, kind=kind, payload=json.loads(payload)) for t, utc, kind, payload in reversed(rows)]


def latest_snapshot(events):
    result = {"telemetry": None, "forecasts": {}, "state": {}, "faults": []}
    for event in events:
        kind, payload = event["kind"], event["payload"]
        if kind == "raw_inbound": result["telemetry"] = payload
        elif kind == "forecast": result["forecasts"][payload["rail_id"]] = payload
        elif kind == "state": result["state"] = payload
        elif kind in {"fault", "error", "reboot"}: result["faults"].append(payload)
    return result
