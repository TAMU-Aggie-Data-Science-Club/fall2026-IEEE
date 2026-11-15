import pytest
from grid_model.contracts import PredictRequest
from grid_model.inference import Predictor
from grid_model.thermal_rc import temperature, eta


def observation(t=0):
    return dict(t_s=t, ambient_temp_c=26., bus_voltage_v=12., rail_voltage_v=12., rail_current_a=1.,
                rail_hotspot_temp_c=40., rail_enabled=True, sensor_valid=True)


def test_persistence_and_quality():
    assert Predictor(model="persistence").predict(PredictRequest("rail_2", [observation()])).predicted_hotspot_plus_300s_c == 40.
    assert Predictor().predict(PredictRequest("rail_2", [])).data_quality == "invalid"
    bad = observation(); bad["rail_hotspot_temp_c"] = None
    assert Predictor().predict(PredictRequest("rail_2", [bad])).predicted_hotspot_plus_60s_c is None


def test_rc_physics():
    assert temperature(26, 26, 10, 100000) == pytest.approx(58)
    assert 26 < temperature(60, 26, 0, 1) < 60
    assert temperature(40, 26, 10, 0) == 40
    assert eta(40, 26, 2) is None
    assert 0 < eta(40, 26, 30) < 600


def test_missing_artifact_falls_back(tmp_path):
    predictor = Predictor(tmp_path / "missing")
    assert predictor.kind == "rc" and predictor.fallback_reason
