from grid_algorithm.replay import replay
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.contracts import load_config
from grid_algorithm.policy import Policy
from grid_model.inference import Predictor


def test_all_replay_rows_passive():
    config = load_config()
    app = Coordinator(config, Predictor(), Policy(config), passive=True)
    frames = list(replay("algorithm/fixtures/esp32_telemetry_replay.csv"))
    assert len(frames) == 2993
    states = {r: [] for r in config}
    for now, frame in frames:
        app.accept(frame, now)
        for rail in frame["rails"]:
            if not states[rail["id"]] or states[rail["id"]][-1] != rail["enabled"]: states[rail["id"]].append(rail["enabled"])
    assert app.commands == []
    assert states == {"rail_1": [True], "rail_2": [True, False, True], "rail_3": [True, False]}
