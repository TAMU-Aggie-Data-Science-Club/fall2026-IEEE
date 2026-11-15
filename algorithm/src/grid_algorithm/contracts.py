from dataclasses import dataclass, asdict
import csv
import math


def boolean(value):
    if value in (True, 1, "1", "true"):
        return True
    if value in (False, 0, "0", "false"):
        return False
    raise ValueError("invalid boolean")


@dataclass(frozen=True)
class RailConfig:
    id: str
    warning: float
    critical: float
    shed_allowed: bool
    priority: str


def load_config(path="algorithm/fixtures/rail_config.csv"):
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    config = {r["rail_id"]: RailConfig(r["rail_id"], float(r["warning_hotspot_c"]),
              float(r["critical_hotspot_c"]), boolean(r["shed_allowed"]), r["load_priority"]) for r in rows}
    if not config or config.get("rail_1") is None or config["rail_1"].shed_allowed:
        raise ValueError("protected rail_1 configuration required")
    if any(not math.isfinite(r.warning) or not math.isfinite(r.critical) or r.warning >= r.critical for r in config.values()):
        raise ValueError("invalid thresholds")
    return config


def number(value):
    return None if value in (None, "") else float(value)


@dataclass
class TelemetryFrame:
    source: str
    seq: int
    uptime_ms: int
    ambient_temp_c: float | None
    bus_voltage_v: float | None
    rails: list[dict]
    fault_flags: list[str]
    last_applied_command_id: str | None = None
    v: int = 1
    type: str = "telemetry"

    def to_dict(self):
        return asdict(self)


def from_csv(row):
    rails = []
    for rid in ("rail_1", "rail_2", "rail_3"):
        t, v, a = [number(row[f"{rid}_{field}"]) for field in ("hotspot_temp_c", "voltage_v", "current_a")]
        rails.append(dict(id=rid, v=v, a=a, hotspot_c=t, enabled=boolean(row[f"{rid}_enabled"]),
                          sensor_valid=all(x is not None for x in (t, v, a))))
    return TelemetryFrame(row["source_device_id"], int(row["packet_seq"]), int(row["uptime_ms"]),
                          number(row["ambient_temp_c"]), number(row["bus_voltage_v"]), rails,
                          row["fault_flags"].split("|") if row["fault_flags"] else [],
                          row["last_applied_command_id"] or None)


def to_long(frame, t_s):
    return [dict(rail_id=r["id"], t_s=t_s, ambient_temp_c=frame["ambient_temp_c"],
                 bus_voltage_v=frame["bus_voltage_v"], rail_voltage_v=r["v"], rail_current_a=r["a"],
                 rail_hotspot_temp_c=r["hotspot_c"], rail_enabled=r["enabled"], sensor_valid=r["sensor_valid"])
            for r in frame["rails"]]


def from_long(rows, source, seq, uptime_ms, fault_flags=None, last_applied_command_id=None):
    """Reassemble one instant; mixing timestamps/ambient/bus is a contract error."""
    if not rows or any(len({row[key] for row in rows}) != 1 for key in ("t_s", "ambient_temp_c", "bus_voltage_v")):
        raise ValueError("long observations must describe one shared instant")
    rails = [dict(id=row["rail_id"], v=row["rail_voltage_v"], a=row["rail_current_a"],
                  hotspot_c=row["rail_hotspot_temp_c"], enabled=boolean(row["rail_enabled"]),
                  sensor_valid=boolean(row["sensor_valid"])) for row in rows]
    return TelemetryFrame(source, seq, uptime_ms, rows[0]["ambient_temp_c"], rows[0]["bus_voltage_v"],
                          rails, fault_flags or [], last_applied_command_id).to_dict()


def to_csv(frame, timestamp_utc):
    """Wide replay export, preserving null/false and one timestamp per packet."""
    row = dict(timestamp_utc=timestamp_utc, uptime_ms=frame["uptime_ms"], packet_seq=frame["seq"],
               source_device_id=frame["source"], ambient_temp_c=frame["ambient_temp_c"], bus_voltage_v=frame["bus_voltage_v"])
    for rail in frame["rails"]:
        for suffix, key in (("voltage_v", "v"), ("current_a", "a"), ("hotspot_temp_c", "hotspot_c")):
            row[f"{rail['id']}_{suffix}"] = rail[key] if rail[key] is not None else ""
        row[f"{rail['id']}_enabled"] = int(rail["enabled"])
    row.update(total_load_current_a=sum(r["a"] or 0 for r in frame["rails"]),
               total_load_power_w=sum((r["a"] or 0) * (r["v"] or 0) for r in frame["rails"]),
               fault_flags="|".join(frame["fault_flags"]), last_applied_command_id=frame["last_applied_command_id"] or "")
    return row


def command_from_csv(row):
    return dict(v=1, type="command", command_id=row["command_id"], source=row["source_device_id"],
                destination=row["destination_device_id"], rail_id=row["rail_id"], action=row["action"],
                enabled=boolean(row["enabled_requested"]), reason=row["reason"])


def ack_from_csv(row):
    return dict(v=1, type="ack", command_id=row["command_id"], source=row["source_device_id"],
                rail_id=row["rail_id"], status=row["status"], enabled=boolean(row["applied_enabled"]),
                controller_uptime_ms=int(row["controller_uptime_ms"]))
