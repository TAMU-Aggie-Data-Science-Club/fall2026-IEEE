"""Strict bounded NDJSON used on fake and physical links alike."""
import json
import math

MAX_LINE = 2048
STATUSES = {"APPLIED", "ALREADY_APPLIED", "REJECTED_PROTECTED", "REJECTED_UNARMED", "REJECTED_UNSAFE", "REJECTED_INVALID", "ERROR"}


def validate(m):
    if not isinstance(m, dict) or type(m.get("v")) is not int or m["v"] != 1:
        raise ValueError("unsupported schema version")
    def finite(x):
        if isinstance(x, float) and not math.isfinite(x):
            raise ValueError("nonfinite number")
        if isinstance(x, dict):
            for value in x.values(): finite(value)
        if isinstance(x, list):
            for value in x: finite(value)
    def text(key):
        if not isinstance(m.get(key), str) or not 0 < len(m[key]) <= 128:
            raise ValueError(f"invalid {key}")
    finite(m)
    kind = m.get("type")
    if kind not in {"telemetry", "command", "ack", "diagnostic", "bridge_status"}:
        raise ValueError("unknown message type")
    text("source")
    if kind in {"command", "ack"}:
        text("command_id"); text("rail_id")
        if type(m.get("enabled")) is not bool:
            raise ValueError("enabled must be JSON boolean")
    if kind == "command":
        text("destination"); text("reason")
        if m.get("action") != "SET_RAIL_ENABLED":
            raise ValueError("unsupported action")
    if kind == "ack":
        if m.get("status") not in STATUSES or type(m.get("controller_uptime_ms")) is not int or not 0 <= m["controller_uptime_ms"] < 2**32:
            raise ValueError("invalid ACK")
    if kind == "telemetry":
        if "controller_session" in m and (type(m["controller_session"]) is not int or not 0 < m["controller_session"] < 2**32):
            raise ValueError("invalid controller boot session")
        for key in ("seq", "uptime_ms"):
            if type(m.get(key)) is not int or not 0 <= m[key] < 2**32:
                raise ValueError(f"invalid {key}")
        rails = m.get("rails")
        if not isinstance(rails, list) or not 0 < len(rails) <= 16:
            raise ValueError("invalid rails")
        if any(not isinstance(r, dict) for r in rails): raise ValueError("invalid rail object")
        ids = [r.get("id") for r in rails]
        if any(not isinstance(r, str) or not r for r in ids) or len(ids) != len(set(ids)):
            raise ValueError("duplicate/invalid rails")
        def bound(value, lo, hi):
            if value is not None and (type(value) not in (float, int) or not lo <= value <= hi):
                raise ValueError("sensor out of range")
        bound(m.get("ambient_temp_c"), -55, 125)
        bound(m.get("bus_voltage_v"), 0, 30)
        if any(k not in m for k in ("ambient_temp_c", "bus_voltage_v", "last_applied_command_id")):
            raise ValueError("missing telemetry fields")
        if m["last_applied_command_id"] is not None and (not isinstance(m["last_applied_command_id"], str) or not m["last_applied_command_id"]):
            raise ValueError("invalid last applied ID")
        if not isinstance(m.get("fault_flags"), list) or any(not isinstance(x, str) for x in m["fault_flags"]):
            raise ValueError("invalid faults")
        for r in rails:
            if any(k not in r for k in ("v", "a", "hotspot_c", "enabled", "sensor_valid")):
                raise ValueError("missing sensor fields")
            if type(r["enabled"]) is not bool or type(r["sensor_valid"]) is not bool:
                raise ValueError("invalid sensor boolean")
            bound(r["v"], 0, 30); bound(r["a"], 0, 10); bound(r["hotspot_c"], -55, 125)
            if r["sensor_valid"] and any(r[k] is None for k in ("v", "a", "hotspot_c")):
                raise ValueError("valid sensor cannot be null")
    return m


def encode(message):
    raw = (json.dumps(validate(message), allow_nan=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_LINE:
        raise ValueError("overlong frame")
    return raw


def decode(raw):
    if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
        raise ValueError("overlong/unframed message")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    try:
        return validate(json.loads(raw.decode("utf-8"), object_pairs_hook=unique))
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("malformed message") from exc


class Framer:
    def __init__(self):
        self.buffer = bytearray()
        self.discard = False
        self.errors = 0

    def feed(self, chunk):
        result = []
        for byte in chunk:
            if byte == 10:
                if not self.discard:
                    try: result.append(decode(bytes(self.buffer) + b"\n"))
                    except ValueError: self.errors += 1
                self.buffer.clear(); self.discard = False
            elif not self.discard:
                self.buffer.append(byte)
                if len(self.buffer) >= MAX_LINE:
                    self.errors += 1; self.buffer.clear(); self.discard = True
        return result
