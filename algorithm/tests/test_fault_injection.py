import pytest
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_model.inference import Predictor


def setup():
    config = load_config(); plant = Plant(config); rig = RigController(plant); bridge = FakeBridge(rig)
    app = Coordinator(config, Predictor(), Policy(config), bridge)
    return plant, rig, bridge, app


def test_lost_ack_retries_identical_id_and_idempotent():
    plant, rig, bridge, app = setup()
    app.accept(bridge.telemetry(), 0)
    bridge.drop_acks = 1
    cmd = app.policy.command("rail_2", False, "test", 0)
    app.send(cmd, 0); app.tick(1)
    assert app.commands[0] == app.commands[1]
    assert app.acks[-1]["status"] == "ALREADY_APPLIED"
    assert not plant.enabled["rail_2"]


def test_disconnect_timeout_never_restores():
    plant, rig, bridge, app = setup()
    app.accept(bridge.telemetry(), 0); bridge.connected = False
    app.send(app.policy.command("rail_2", False, "test", 0), 0)
    for second in (1, 3, 7): app.tick(second)
    assert app.policy.state["rail_2"] == "FAULT"
    assert all(not c["enabled"] for c in app.commands)


def test_duplicate_reboot_and_stale():
    plant, rig, bridge, app = setup()
    plant.time = 10
    frame = bridge.telemetry()
    assert app.accept(frame, 10)
    assert not app.accept(frame, 11)
    rig.reboot()
    assert not app.accept(bridge.telemetry(), 12)
    assert not app.armed_session and not any(plant.enabled.values())
    app.tick(20)
    assert "stale telemetry" in app.errors


def test_sensor_failure_local_cutoff():
    plant, rig, bridge, app = setup()
    plant.sensor_faults.add("rail_2")
    app.accept(bridge.telemetry(), 0)
    assert not plant.enabled["rail_2"] and not app.commands
    assert app.forecasts["rail_2"]["data_quality"] == "invalid"


def test_restore_interlock_and_protected():
    plant, rig, bridge, app = setup()
    assert bridge.send(app.policy.command("rail_1", False, "test", 0))["status"] == "REJECTED_PROTECTED"
    cmd = app.policy.command("rail_2", False, "test", 0); bridge.send(cmd)
    restore = app.policy.command("rail_2", True, "MANUAL_RESTORE_AFTER_COOLDOWN", 1, "operator")
    assert bridge.send(restore)["status"] == "REJECTED_UNSAFE"
    plant.time = 70
    restore = app.policy.command("rail_2", True, "MANUAL_RESTORE_AFTER_COOLDOWN", 70, "operator")
    assert bridge.send(restore)["status"] == "APPLIED"


def test_critical_cutoff_without_laptop():
    plant, rig, bridge, app = setup()
    plant.temps["rail_2"] = 81; plant.temps["rail_1"] = 81
    rig.protect()
    assert not plant.enabled["rail_2"] and plant.enabled["rail_1"]


def test_conflicting_duplicate_rejected():
    plant, rig, bridge, app = setup()
    cmd = app.policy.command("rail_2", False, "test", 0)
    bridge.send(cmd)
    assert bridge.send(dict(cmd, enabled=True))["status"] == "REJECTED_INVALID"
    assert not plant.enabled["rail_2"]
