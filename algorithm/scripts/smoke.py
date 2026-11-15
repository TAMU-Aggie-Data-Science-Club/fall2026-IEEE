"""Run the offline loop and verify its machine-readable acceptance summary."""
import json
from grid_algorithm.cli import simulate
from grid_algorithm.contracts import load_config


if __name__ == "__main__":
    result = simulate(load_config(), duration=900)
    assert set(result["shed"]) == {"rail_2", "rail_3"}
    assert result["protected_rail_sheds"] == result["automatic_restores"] == 0
    assert len(result["acks"]) == 2
    for rail in result["shed"]:
        assert result["cooling"][rail]["current_a"] == 0
        assert result["cooling"][rail]["after_60s_c"] < result["shed"][rail]["hotspot_c"]
    print(json.dumps(result, indent=2))
