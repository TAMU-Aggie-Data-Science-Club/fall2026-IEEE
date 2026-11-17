from collections import deque
from grid_model.contracts import PredictRequest
from .contracts import to_long


class Coordinator:
    def __init__(self, config, predictor, policy, transport=None, log=None, passive=False, stale_s=5, hardware_domain="demo_rc"):
        self.config, self.predictor, self.policy = config, predictor, policy
        self.transport, self.log, self.passive, self.stale_s = transport, log, passive, stale_s
        lookback = predictor.metadata.get("hyperparameters", {}).get("lookback_s", 300)
        self.histories = {r: deque(maxlen=lookback + 1) for r in config}
        self.last_seq = self.last_uptime = self.last_received = None
        self.errors = []; self.commands = []; self.acks = []; self.forecasts = {}
        self.armed_session = True
        self.hardware_domain = hardware_domain

    def record(self, kind, payload, now):
        if self.log: self.log.write(kind, payload, now)

    def send(self, command, now):
        if getattr(self.predictor, "hardware_domain", "demo_rc") != self.hardware_domain:
            self.record("fault", {"message": "model/hardware domain mismatch: actuation blocked"}, now)
            return
        self.commands.append(command); self.record("command", command, now)
        try:
            ack = self.transport.send(command)
            self.record("bridge_status", {"connected": True, "command_id": command["command_id"]}, now)
            if ack: self.receive_ack(ack, now)
        except (ConnectionError, OSError) as exc:
            self.errors.append(str(exc)); self.record("error", {"message": str(exc)}, now)

    def receive_ack(self, ack, now):
        matched = self.policy.ack(ack)
        self.acks.append(ack); self.record("ack", dict(ack, matched=matched), now)

    def accept(self, frame, now):
        self.record("raw_inbound", frame, now)
        if frame["source"] != "esp32_rig_01":
            self.errors.append("unexpected telemetry source")
            self.record("fault", {"message": self.errors[-1]}, now)
            return False
        seq, uptime = frame["seq"], frame["uptime_ms"]
        if self.last_seq is not None:
            delta = (seq - self.last_seq) % 2**32
            rollover = self.last_uptime > 0xf0000000 and uptime < 0x10000000
            reboot = uptime < self.last_uptime and not rollover
            if reboot:
                self.policy.reset_session()
                for h in self.histories.values(): h.clear()
                self.record("reboot", {"previous_uptime": self.last_uptime}, now)
                self.last_seq, self.last_uptime, self.last_received = seq, uptime, now
                self.armed_session = False
                return False
            if delta == 0 or delta > 2**31:
                self.errors.append("duplicate/out-of-order packet"); return False
            if delta > 1: self.record("packet_gap", {"missing": delta - 1}, now)
        if self.last_received is not None and now <= self.last_received:
            self.errors.append("nonmonotonic arrival"); return False
        self.last_seq, self.last_uptime, self.last_received = seq, uptime, now
        ids = {r["id"] for r in frame["rails"]}
        if ids != set(self.config):
            self.errors.append("missing/unconfigured rails"); self.record("fault", {"message": self.errors[-1]}, now)
            return False
        faulted = bool(frame["fault_flags"])
        for observation, rail in zip(to_long(frame, now), frame["rails"]):
            rid = rail["id"]
            self.histories[rid].append(observation)
            forecast = self.predictor.predict(PredictRequest(rid, list(self.histories[rid])))
            if faulted: forecast.data_quality = "invalid"
            self.forecasts[rid] = forecast.to_dict()
            self.record("observation", observation, now); self.record("forecast", forecast.to_dict(), now)
            compatible = forecast.hardware_domain == self.hardware_domain and forecast.actuation_eligible
            if not self.passive and self.armed_session and not faulted and compatible:
                command = self.policy.decide(rail, forecast, now)
                if command: self.send(command, now)
            elif not rail["sensor_valid"]:
                self.policy.alarms.append(f"sensor fault: {rid}")
        self.record("state", {"states": self.policy.state, "alarms": self.policy.alarms[-10:], "passive": self.passive}, now)
        return True

    def tick(self, now):
        if self.last_received is None or now - self.last_received > self.stale_s:
            if not self.errors or self.errors[-1] != "stale telemetry":
                self.errors.append("stale telemetry"); self.record("fault", {"message": "stale telemetry"}, now)
            for r in self.policy.state: self.policy.state[r] = "FAULT"
            return
        if not self.passive and self.armed_session:
            for command in self.policy.retries(now): self.send(command, now)
