import numpy as np
import pytest
from grid_model.crossing import first_crossing, detection_metrics
from grid_model.evaluation import score


def test_crossing_time_peak_and_units():
    assert first_crossing([0,60,300],[70,90,75],80) == 30
    assert first_crossing([0,60,300],[40,50,60],80) is None
    with pytest.raises(ValueError): first_crossing([1,0],[70,90],80)
    metrics = detection_metrics([70,85],[[90,75],[85,85]],[True,True],[30,0])
    assert metrics["future_onset"]["true_positives"] == 1
    assert metrics["future_onset"]["count"] == 1 and metrics["currently_over_threshold"] == 1
    assert metrics["crossing_time"]["mae_s"] == 0


def test_physics_trajectory_crossing_overrides_cool_endpoints():
    metrics=detection_metrics([70.],[[75.,74.]],[True],[150.],predicted_eta=[140.])
    assert metrics["future_onset"]["true_positives"] == 1
    assert metrics["crossing_time"]["mae_s"] == 10.
    already_hot=detection_metrics([90.],[[75.,74.]],[True],[0.],predicted_eta=[None])
    assert already_hot["all_windows"]["true_positives"] == 1
    with pytest.raises(ValueError): detection_metrics([70.],[[float("nan"),80.]],[True])


def test_model_predictions_not_shared_current_temperature_proxy():
    class Candidate:
        def predict(self,x): return np.array([[75.,85.],[72.,77.]])
    rows = [dict(rail_hotspot_temp_c=70.,rail_power_w=10.,ambient_temp_c=26.,target_crosses_80c_next_300s=label,
                 target_time_to_80c_within_600s=eta,scenario_id="A") for label,eta in [(1,200),(0,-1)]]
    windows = [(np.zeros(2),np.zeros((60,11)),[75,85] if i==0 else [72,77],row) for i,row in enumerate(rows)]
    ridge, persistence = score("ridge",windows,Candidate()),score("persistence",windows)
    assert ridge["detection"]["future_onset"]["recall"] == 1.
    assert persistence["detection"]["future_onset"]["recall"] == 0.
    assert persistence["crossing"]["false_negatives"] == 1
    assert ridge["prediction_sha256"] != persistence["prediction_sha256"]
