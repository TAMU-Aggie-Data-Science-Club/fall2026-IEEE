import logging
import pytest
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.persistence import EventLog
from grid_model.inference import Predictor


def test_dashboard_updates_across_full_1800_sample_simulation(tmp_path,caplog):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    config=load_config(); plant=Plant(config); bridge=FakeBridge(RigController(plant))
    path=tmp_path/"live.sqlite"; log=EventLog(path)
    app=Coordinator(config,Predictor(),Policy(config),bridge,log)
    dashboard=AppTest.from_file("algorithm/dashboard/app.py").run(timeout=30)
    dashboard.sidebar.text_input[0].set_value(str(path))
    temperatures=[]
    with caplog.at_level(logging.WARNING):
        for chunk in range(3):
            for _ in range(600):
                app.accept(bridge.telemetry(),plant.time); app.tick(plant.time); plant.step()
            dashboard.run(timeout=30)
            assert not dashboard.exception
            temperatures.append([metric.value for metric in dashboard.metric])
    assert plant.time == 1800 and len(app.acks) == 2
    assert temperatures[0] != temperatures[1] != temperatures[2]
    assert not [r for r in caplog.records if r.levelno>=logging.WARNING and "fragment" in r.getMessage().lower()]
    log.close()
