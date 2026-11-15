import argparse
import json
import time
from pathlib import Path
from .contracts import load_config
from .policy import Policy
from .model_client import Predictor
from .coordinator import Coordinator
from .persistence import EventLog
from .simulator import Plant, RigController
from .transport import FakeBridge, SerialTransport
from .replay import replay


def simulate(config, duration=1800, scenario="dual_overload", artifact=None, seed=42, log=None, speed=0, settings=None):
    settings = settings or {}
    plant = Plant(config, scenario, seed)
    controller = RigController(plant, min_off_s=settings.get("min_off_s", 60), hysteresis=settings.get("restore_hysteresis_c", 5))
    bridge = FakeBridge(controller)
    policy = Policy(config, persistence=settings.get("prediction_persistence", 2), cooldown_s=settings.get("cooldown_s", 10),
                    ack_timeout_s=settings.get("ack_timeout_s", 1), max_attempts=settings.get("max_attempts", 3))
    app = Coordinator(config, Predictor(artifact), policy, bridge, log, stale_s=settings.get("stale_s", 5))
    peaks = dict(plant.temps); at_shed = {}; cooling = {}
    for second in range(duration):
        frame = bridge.telemetry()
        app.accept(frame, float(second)); app.tick(float(second))
        for rid in config:
            peaks[rid] = max(peaks[rid], plant.temps[rid])
            if not plant.enabled[rid] and rid not in at_shed:
                at_shed[rid] = {"t_s": second, "hotspot_c": plant.temps[rid]}
            if rid in at_shed and second >= at_shed[rid]["t_s"] + 60 and rid not in cooling:
                cooling[rid] = {"after_60s_c": plant.temps[rid], "current_a": plant.current(rid)}
        plant.step()
        if speed: time.sleep(1 / speed)
    result = dict(synthetic_only=True, mode="closed_loop", model=app.predictor.kind,
                  fallback_reason=app.predictor.fallback_reason, samples=duration, peaks_c=peaks, shed=at_shed,
                  cooling=cooling, commands=app.commands, acks=app.acks,
                  final_temperature_c=plant.temps, states=app.policy.state,
                  protected_rail_sheds=sum(c["rail_id"] == "rail_1" and not c["enabled"] for c in app.commands),
                  automatic_restores=sum(c["enabled"] for c in app.commands))
    if log: log.write("summary", result, duration)
    return result


def main():
    parser = argparse.ArgumentParser(description="IEEE x ADSC synthetic thermal demo; hardware monitor only")
    parser.add_argument("--rail-config", default="algorithm/fixtures/rail_config.csv")
    parser.add_argument("--config", default="algorithm/configs/demo.yaml", help="JSON-compatible YAML settings")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("simulate")
    p.add_argument("--scenario", choices=["normal", "ramp", "abrupt_overload", "hot_ambient", "dual_overload"], default="dual_overload")
    p.add_argument("--duration-s", type=int, default=1800); p.add_argument("--speed", type=float, default=0)
    p.add_argument("--artifact"); p.add_argument("--seed", type=int, default=42)
    p.add_argument("--log", default="algorithm/runs/demo.sqlite")
    p = sub.add_parser("replay"); p.add_argument("--data", default="algorithm/fixtures/esp32_telemetry_replay.csv")
    p.add_argument("--speed", type=float, default=0); p.add_argument("--limit", type=int); p.add_argument("--start-offset", type=float, default=0)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--log", default="algorithm/runs/replay.sqlite")
    p = sub.add_parser("live"); p.add_argument("--port", required=True); p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--monitor-only", action="store_true", default=True); p.add_argument("--duration-s", type=float)
    p.add_argument("--log", default="algorithm/runs/live.sqlite")
    p = sub.add_parser("export"); p.add_argument("--log", required=True); p.add_argument("--output", required=True)
    args = parser.parse_args()
    log = None
    try:
        if getattr(args, "speed", 0) < 0 or (getattr(args, "duration_s", 1) is not None and getattr(args, "duration_s", 1) <= 0):
            raise ValueError("speed must be nonnegative; duration must be positive")
        config = load_config(args.rail_config)
        settings = json.loads(Path(args.config).read_text(encoding="utf-8"))
        for name in ("prediction_persistence", "max_attempts", "ack_timeout_s", "stale_s", "min_off_s"):
            if not isinstance(settings[name], (int, float)) or settings[name] <= 0:
                raise ValueError(f"{name} must be positive")
        log = EventLog(args.log)
        if args.command == "simulate":
            result = simulate(config, args.duration_s, args.scenario, args.artifact, args.seed, log, args.speed, settings)
        elif args.command == "replay":
            app = Coordinator(config, Predictor(), Policy(config), log=log, passive=True)
            count = 0; transitions = []; prior = {}; previous_time = None
            for now, frame in replay(args.data, args.limit, args.start_offset):
                if args.speed and previous_time is not None: time.sleep((now - previous_time) / args.speed)
                previous_time = now
                app.accept(frame, now); count += 1
                for rail in frame["rails"]:
                    if rail["id"] in prior and prior[rail["id"]] != rail["enabled"]:
                        transitions.append(dict(t_s=now, rail_id=rail["id"], enabled=rail["enabled"], source="recorded fixture"))
                    prior[rail["id"]] = rail["enabled"]
            result = dict(mode="passive_replay", synthetic_only=True, samples=count, generated_commands=0, recorded_transitions=transitions)
        elif args.command == "export":
            log.export(args.output); result = {"exported": args.output}
        else:
            transport = SerialTransport(args.port, args.baud, monitor_only=True)
            app = Coordinator(config, Predictor(), Policy(config), transport, log, passive=True)
            start = time.monotonic()
            try:
                while args.duration_s is None or time.monotonic() - start < args.duration_s:
                    now = time.monotonic()
                    for frame in transport.receive(now):
                        if frame["type"] == "telemetry": app.accept(frame, now)
                        elif frame["type"] == "ack": app.receive_ack(frame, now)
                        else: app.record("bridge_status", frame, now)
                    app.tick(now); time.sleep(.02)
            except KeyboardInterrupt: pass
            finally: transport.close()
            result = {"monitor_only": True, "errors": app.errors}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, ImportError) as exc: parser.exit(2, f"error: {exc}\n")
    finally:
        if log: log.close()


if __name__ == "__main__": main()
