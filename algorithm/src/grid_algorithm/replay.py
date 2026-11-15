import csv
from datetime import datetime
from .contracts import from_csv
from .protocol import encode, decode


def replay(path, limit=None, start_offset=0):
    with open(path, newline="", encoding="utf-8") as stream:
        first = None; count = 0
        for row in csv.DictReader(stream):
            timestamp = datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00")).timestamp()
            if first is None: first = timestamp
            virtual_time = timestamp - first
            if virtual_time < start_offset: continue
            if limit is not None and count >= limit: break
            yield virtual_time, decode(encode(from_csv(row).to_dict()))
            count += 1
