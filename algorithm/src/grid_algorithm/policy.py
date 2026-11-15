from dataclasses import dataclass
import uuid


@dataclass
class Pending:
    command: dict
    sent_at: float
    attempts: int = 1
    acked: bool = False


class Policy:
    def __init__(self, config, persistence=2, cooldown_s=10, ack_timeout_s=1, max_attempts=3):
        self.config = config
        self.persistence, self.cooldown_s = persistence, cooldown_s
        self.ack_timeout_s, self.max_attempts = ack_timeout_s, max_attempts
        self.state = {r: "UNKNOWN" for r in config}
        self.pending = {}
        self.count = {r: 0 for r in config}
        self.last_action = {r: -1e9 for r in config}
        self.alarms = []
        self.run_id = uuid.uuid4().hex[:12]
        self.counter = 0

    def command(self, rid, enabled, reason, now, operator=None):
        self.counter += 1
        cmd = dict(v=1, type="command", command_id=f"{self.run_id}-{self.counter:06d}", source="laptop",
                   destination="esp32_rig_01", action="SET_RAIL_ENABLED", rail_id=rid, enabled=enabled, reason=reason)
        if operator: cmd["operator"] = operator
        self.pending[rid] = Pending(cmd, now)
        self.state[rid] = "RESTORE_REQUESTED" if enabled else "SHED_REQUESTED"
        self.last_action[rid] = now
        return cmd

    def decide(self, rail, forecast, now):
        rid = rail["id"]; config = self.config[rid]
        pending = self.pending.get(rid)
        if pending:
            if pending.acked and rail["enabled"] == pending.command["enabled"]:
                self.state[rid] = "ON" if rail["enabled"] else "SHED_CONFIRMED"
                del self.pending[rid]
            elif pending.acked:
                self.state[rid] = "FAULT"; self.alarms.append(f"contradictory relay state: {rid}")
            return None
        if self.state[rid] == "FAULT": return None
        self.state[rid] = "ON" if rail["enabled"] else "SHED_CONFIRMED"
        valid = rail["sensor_valid"] and rail["hotspot_c"] is not None
        if not valid:
            self.count[rid] = 0; self.alarms.append(f"sensor fault: {rid}"); return None
        predicted = forecast.predicted_hotspot_plus_300s_c
        trigger = (forecast.data_quality == "good" and predicted is not None and predicted >= config.warning)
        measured = rail["hotspot_c"] >= config.warning
        self.count[rid] = self.count[rid] + 1 if trigger or measured else 0
        if not config.shed_allowed:
            if measured or trigger: self.alarms.append(f"protected load alarm: {rid}")
            return None
        if rail["enabled"] and self.count[rid] >= self.persistence and now - self.last_action[rid] >= self.cooldown_s:
            reason = "MEASURED_WARNING" if measured else f"PREDICTED_WARNING_THRESHOLD_300S:{forecast.model_id}"
            return self.command(rid, False, reason, now)
        return None

    def ack(self, ack):
        rid = ack["rail_id"]; pending = self.pending.get(rid)
        if not pending or ack["command_id"] != pending.command["command_id"] or ack["source"] != "esp32_rig_01": return False
        if ack["status"] in {"APPLIED", "ALREADY_APPLIED"} and ack["enabled"] == pending.command["enabled"]:
            pending.acked = True
        else:
            self.state[rid] = "FAULT"; del self.pending[rid]
        return True

    def retries(self, now):
        commands = []
        for rid, pending in list(self.pending.items()):
            timeout = self.ack_timeout_s * 2 ** (pending.attempts - 1)
            if now - pending.sent_at < timeout: continue
            if pending.acked or pending.attempts >= self.max_attempts:
                self.state[rid] = "FAULT"; self.alarms.append(f"ACK/observation timeout: {rid}")
                del self.pending[rid]
            else:
                pending.attempts += 1; pending.sent_at = now
                commands.append(pending.command)
        return commands

    def manual_restore(self, rid, now, operator, safe_to_restore):
        if not operator or not safe_to_restore or self.state[rid] != "SHED_CONFIRMED" or rid in self.pending:
            raise PermissionError("explicit operator and controller safe-to-restore required")
        return self.command(rid, True, "MANUAL_RESTORE_AFTER_COOLDOWN", now, operator)

    def reset_session(self):
        self.pending.clear()
        self.count = {r: 0 for r in self.config}
        self.state = {r: "UNKNOWN" for r in self.config}
