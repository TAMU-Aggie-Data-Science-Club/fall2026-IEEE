from grid_algorithm.cli import simulate
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.policy import Policy
from grid_algorithm.transport import FakeBridge


def test_complete_closed_loop():
    result = simulate(load_config(), duration=900)
    assert set(result["shed"]) == {"rail_2", "rail_3"}
    assert len(result["commands"]) == len(result["acks"]) == 2
    assert result["protected_rail_sheds"] == result["automatic_restores"] == 0
    for rid in result["shed"]:
        assert result["cooling"][rid]["current_a"] == 0
        assert result["final_temperature_c"][rid] < result["cooling"][rid]["after_60s_c"] < result["shed"][rid]["hotspot_c"]
    assert all(s == "SHED_CONFIRMED" for r, s in result["states"].items() if r != "rail_1")


def test_no_instant_cooling_and_real_switch():
    config = load_config(); plant = Plant(config); controller = RigController(plant)
    bridge = FakeBridge(controller); policy = Policy(config)
    before = plant.temps["rail_2"]
    command = policy.command("rail_2", False, "test", 0)
    assert bridge.send(command)["status"] == "APPLIED"
    assert plant.temps["rail_2"] == before
    rail = bridge.telemetry()["rails"][1]
    assert rail["a"] == rail["v"] == 0
    plant.step()
    assert 26 < plant.temps["rail_2"] < before


def test_normal_no_shedding():
    assert simulate(load_config(), duration=400, scenario="normal")["commands"] == []
