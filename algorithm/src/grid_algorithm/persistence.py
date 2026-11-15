import csv
import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone


class EventLog:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, t_s REAL, utc TEXT, kind TEXT, payload TEXT)")

    def write(self, kind, payload, now):
        # Streamlit reruns use a new script thread; serialize the shared connection.
        with self.lock:
            self.db.execute("INSERT INTO events(t_s,utc,kind,payload) VALUES (?,?,?,?)",
                            (now, datetime.now(timezone.utc).isoformat(), kind, json.dumps(payload, allow_nan=False)))
            self.db.commit()

    def export(self, path):
        with self.lock, open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["id", "t_s", "utc", "kind", "payload"])
            writer.writerows(self.db.execute("SELECT * FROM events ORDER BY id"))

    def close(self):
        with self.lock: self.db.close()
