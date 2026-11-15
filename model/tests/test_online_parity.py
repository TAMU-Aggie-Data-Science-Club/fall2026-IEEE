import numpy as np
from grid_model.features import features, sequence
from grid_model.contracts import PredictRequest
from grid_model.inference import Predictor


def test_causal_prefix_and_short_gap_mask():
    history = [dict(t_s=t, ambient_temp_c=26., bus_voltage_v=12., rail_voltage_v=12., rail_current_a=1.,
                    rail_hotspot_temp_c=40 + t / 100, rail_enabled=True, sensor_valid=True) for t in range(300)]
    before = features(history)
    # Adding future truth as unused metadata cannot alter causal feature extraction.
    for row in history: row["target_hotspot_temp_plus_300s_c"] = -999
    np.testing.assert_array_equal(features(history), before)
    history[100]["rail_hotspot_temp_c"] = None
    history[100]["sensor_valid"] = False
    seq, missing, invalid = sequence(history)
    assert np.isfinite(seq).all() and missing > 0 and invalid > 0


def test_explicit_stale_input_is_invalid():
    observation = dict(t_s=0, ambient_temp_c=26., rail_voltage_v=12., rail_current_a=1.,
                       rail_hotspot_temp_c=40., rail_enabled=True, sensor_valid=True)
    assert Predictor().predict(PredictRequest("rail_2", [observation], current_t_s=10)).data_quality == "invalid"
