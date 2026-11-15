from grid_algorithm.protocol import Framer, encode
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge, SerialTransport
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_model.inference import Predictor
import pytest


def test_monitor_only_blocks_commands():
    with pytest.raises(PermissionError): SerialTransport("operator-port").send({})


def test_bridge_cannot_impersonate_rig_telemetry():
    config = load_config(); bridge = FakeBridge(RigController(Plant(config)))
    app = Coordinator(config, Predictor(), Policy(config), bridge)
    frame = dict(bridge.telemetry(), source="esp32_bridge_01")
    assert not app.accept(frame, 0)
    assert app.commands == [] and app.last_received is None


def test_out_of_order_seq_wrap_uptime_rollover():
    config = load_config(); plant = Plant(config); bridge = FakeBridge(RigController(plant))
    app = Coordinator(config, Predictor(), Policy(config), bridge)
    frame = bridge.telemetry()
    frame.update(seq=2**32 - 1, uptime_ms=2**32 - 1000)
    assert app.accept(frame, 0)
    frame = dict(frame, seq=0, uptime_ms=0)
    assert app.accept(frame, 1) and app.armed_session
    assert not app.accept(dict(frame, seq=2**32 - 1), 2)


def test_ack_timeout_bounded_and_late_ack_ignored():
    policy = Policy(load_config())
    cmd = policy.command("rail_2", False, "test", 0)
    assert policy.retries(1) == [cmd]
    assert policy.retries(3) == [cmd]
    assert policy.retries(7) == [] and policy.state["rail_2"] == "FAULT"
    assert not policy.ack(dict(command_id=cmd["command_id"], rail_id="rail_2", source="esp32_rig_01", status="APPLIED", enabled=False))


def test_contradictory_applied_state_fault():
    policy = Policy(load_config()); cmd = policy.command("rail_2", False, "test", 0)
    policy.ack(dict(command_id=cmd["command_id"], rail_id="rail_2", source="esp32_rig_01", status="APPLIED", enabled=False))
    from grid_model.contracts import PredictResponse
    forecast = PredictResponse("rail_2", 40, 40, 40, None, "persistence", "1", "good")
    policy.decide(dict(id="rail_2", enabled=True, sensor_valid=True, hotspot_c=40), forecast, 1)
    assert policy.state["rail_2"] == "FAULT"
