import pytest
from grid_algorithm.contracts import load_config
from grid_algorithm.policy import Policy
from grid_model.inference import Predictor
from grid_model.contracts import PredictRequest


def forecast():
    return Predictor().predict(PredictRequest("rail_2", [dict(t_s=0, rail_hotspot_temp_c=70., ambient_temp_c=26.,
        rail_current_a=2., rail_voltage_v=12., rail_enabled=True, sensor_valid=True)]))


def test_protected_persistence_and_no_restore():
    policy = Policy(load_config())
    for rid in ("rail_1", "rail_2", "rail_3"):
        rail = dict(id=rid, enabled=True, hotspot_c=70., sensor_valid=True)
        assert policy.decide(rail, forecast(), 0) is None
        cmd = policy.decide(rail, forecast(), 1)
        assert (cmd is None) == (rid == "rail_1")
        if cmd: assert not cmd["enabled"]
    with pytest.raises(PermissionError): policy.manual_restore("rail_2", 5, "", False)


def test_ack_cannot_complete_wrong_rail():
    policy = Policy(load_config())
    cmd = policy.command("rail_2", False, "test", 0)
    ack = dict(command_id=cmd["command_id"], rail_id="rail_3", source="esp32_rig_01", status="APPLIED", enabled=False)
    assert not policy.ack(ack)
    ack["rail_id"] = "rail_2"
    assert policy.ack(ack)
    assert policy.state["rail_2"] == "SHED_REQUESTED"
    policy.decide(dict(id="rail_2", enabled=False, sensor_valid=True, hotspot_c=50), forecast(), 1)
    assert policy.state["rail_2"] == "SHED_CONFIRMED"
