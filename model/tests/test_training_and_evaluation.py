import json
import numpy as np
import pytest
from grid_model.training import train, evaluate
from grid_model.inference import Predictor
from grid_model.contracts import PredictRequest
from grid_model.data import load


def test_ridge_reload(tmp_path):
    metadata = train("ridge", "model/data/model_training_timeseries.csv", tmp_path, quick=True)
    assert metadata["synthetic_only"] and not metadata["rail_id_used"]
    predictor = Predictor(tmp_path)
    df = load()
    records = df[(df.scenario_id == "S001") & (df.rail_id == "rail_2")].iloc[300:600].rename(columns={"elapsed_s": "t_s"}).to_dict("records")
    response = predictor.predict(PredictRequest("rail_2", records))
    assert response.data_quality in {"good", "degraded"}
    assert np.isfinite(response.predicted_hotspot_plus_300s_c)
    result = evaluate(tmp_path, "test")
    assert result["horizons"]["60"]["mae_c"] >= 0
    assert (tmp_path / "metrics-test.json").exists()


@pytest.mark.parametrize("kind", ["lstm", "transformer"])
def test_neural_cpu_training_reload(kind, tmp_path):
    pytest.importorskip("torch")
    metadata = train(kind, "model/data/model_training_timeseries.csv", tmp_path, quick=True, epochs=1)
    assert metadata["normalization"]["epochs_completed"] == 1
    from grid_model.neural import NeuralForecaster
    import torch
    net = NeuralForecaster(kind)
    net.load_state_dict(torch.load(tmp_path / "weights.pt", weights_only=True))
    assert net(torch.zeros(2, 60, 11)).shape == (2, 2)
