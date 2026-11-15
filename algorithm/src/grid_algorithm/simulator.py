"""Mutable plant and controller-local interlocks, independent of training labels."""
import random
from collections import OrderedDict
from grid_model.thermal_rc import temperature
from .contracts import TelemetryFrame


class Plant:
    def __init__(self, config, scenario="dual_overload", seed=42):
        self.config, self.scenario = config, scenario
        self.random = random.Random(seed)
        self.time = 0.
        self.temps = {r: 35. for r in config}
        self.enabled = {r: True for r in config}
        self.off_since = {r: -1e9 for r in config}
        self.last_command = None
        self.seq = 0
        self.ambient = 40. if scenario == "hot_ambient" else 26.
        self.sensor_faults = set()

    def current(self, rid):
        if not self.enabled[rid]: return 0.
        if rid == "rail_1" or self.scenario == "normal": return .6
        if self.scenario == "ramp": return min(2., .6 + self.time / 500)
        if self.scenario == "abrupt_overload": return 2. if self.time >= 100 and rid == "rail_2" else .6
        return 2. if self.time >= 100 else .6

    def sample(self):
        self.seq = (self.seq + 1) % 2**32
        bus = 12. - .025 * sum(self.current(r) for r in self.config)
        rails = [dict(id=r, v=round(bus if self.enabled[r] else 0., 3), a=round(self.current(r), 3),
                      hotspot_c=None if r in self.sensor_faults else round((self.temps[r] + self.random.gauss(0, .01)) * 16) / 16,
                      enabled=self.enabled[r], sensor_valid=r not in self.sensor_faults) for r in self.config]
        return TelemetryFrame("esp32_rig_01", self.seq, int(self.time * 1000) % 2**32, self.ambient,
                              bus, rails, [f"SENSOR:{r}" for r in self.sensor_faults], self.last_command).to_dict()

    def step(self, dt=1.):
        if dt <= 0: raise ValueError("positive time step required")
        bus = 12. - .025 * sum(self.current(r) for r in self.config)
        for r in self.config:
            self.temps[r] = temperature(self.temps[r], self.ambient, bus * self.current(r), dt)
        self.time += dt


class RigController:
    def __init__(self, plant, armed=True, min_off_s=60, hysteresis=5):
        self.plant, self.armed = plant, armed
        self.min_off_s, self.hysteresis = min_off_s, hysteresis
        self.recent = OrderedDict()

    def safe_to_restore(self, rid):
        p = self.plant
        return (rid in p.config and rid not in p.sensor_faults and
                p.temps[rid] < p.config[rid].warning - self.hysteresis and
                p.time - p.off_since[rid] >= self.min_off_s)

    def protect(self):
        p = self.plant
        for r, c in p.config.items():
            if c.shed_allowed and p.enabled[r] and (p.temps[r] >= c.critical or p.current(r) > 3 or r in p.sensor_faults):
                p.enabled[r] = False; p.off_since[r] = p.time

    def apply(self, cmd):
        p, rid = self.plant, cmd["rail_id"]
        cid = cmd["command_id"]
        if cid in self.recent:
            prior, ack = self.recent[cid]
            if prior != cmd:
                return dict(ack, status="REJECTED_INVALID")
            # Actual current state, not a cached fictional relay state.
            return dict(ack, status="ALREADY_APPLIED" if p.enabled[rid] == cmd["enabled"] else "REJECTED_UNSAFE",
                        enabled=p.enabled[rid], controller_uptime_ms=int(p.time * 1000))
        status = "APPLIED"
        if rid not in p.config or cmd.get("destination") != "esp32_rig_01": status = "REJECTED_INVALID"
        elif not self.armed: status = "REJECTED_UNARMED"
        elif not p.config[rid].shed_allowed: status = "REJECTED_PROTECTED"
        elif cmd["enabled"] and (not cmd.get("operator") or not cmd["reason"].startswith("MANUAL_RESTORE") or not self.safe_to_restore(rid)):
            status = "REJECTED_UNSAFE"
        elif rid in p.sensor_faults: status = "REJECTED_UNSAFE"
        elif p.enabled[rid] == cmd["enabled"]: status = "ALREADY_APPLIED"
        if status == "APPLIED":
            p.enabled[rid] = cmd["enabled"]
            if not cmd["enabled"]: p.off_since[rid] = p.time
            p.last_command = cid
        ack = dict(v=1, type="ack", command_id=cid, source="esp32_rig_01", rail_id=rid, status=status,
                   enabled=p.enabled.get(rid, False), controller_uptime_ms=int(p.time * 1000) % 2**32)
        if rid in p.config:
            self.recent[cid] = (dict(cmd), ack)
            if len(self.recent) > 64: self.recent.popitem(last=False)
        return ack

    def reboot(self):
        for rid in self.plant.enabled:
            self.plant.enabled[rid] = False
            self.plant.off_since[rid] = self.plant.time
        self.recent.clear(); self.armed = False
        self.plant.seq = 0; self.plant.time = 0
