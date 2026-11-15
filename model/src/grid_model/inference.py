from pathlib import Path
import json
import numpy as np
from .contracts import PredictRequest, PredictResponse
from .features import sequence, features
from .thermal_rc import temperature, eta


class Predictor:
    def __init__(self, artifact=None, model="rc", enforce_selection=True):
        self.kind, self.model, self.metadata = model, None, {"version": "0.1.0"}
        self.fallback_reason = None
        if artifact:
            try:
                path = Path(artifact)
                self.metadata = json.loads((path / "metadata.json").read_text())
                self.kind = self.metadata["model"]
                if self.kind == "ridge":
                    import joblib
                    self.model = joblib.load(path / "model.joblib")
                elif self.kind in {"lstm", "transformer"}:
                    import torch
                    from .neural import NeuralForecaster
                    torch.set_num_threads(2)
                    self.model = NeuralForecaster(self.kind)
                    self.model.load_state_dict(torch.load(path / "weights.pt", map_location="cpu", weights_only=True))
                    self.model.eval()
                if enforce_selection and self.metadata.get("validation_accepted") is False:
                    self.fallback_reason = "candidate worse than persistence on validation; using RC"
                    self.kind, self.model = "rc", None
            except (OSError, ValueError, KeyError, ImportError, RuntimeError) as exc:
                self.fallback_reason = f"artifact unavailable: {exc}; using RC"
                self.kind, self.model = "rc", None

    def predict(self, request: PredictRequest):
        obs = request.observations
        last = obs[-1] if obs else {}
        observed = last.get("rail_hotspot_temp_c")
        if not isinstance(observed, (float, int)) or not np.isfinite(observed): observed = None
        def result(a=None, b=None, e=None, quality="invalid"):
            return PredictResponse(request.rail_id, observed, a, b, e, self.kind,
                                   self.metadata.get("version", "0.1.0"), quality)
        if not obs or not last.get("sensor_valid") or observed is None:
            return result()
        if request.current_t_s is not None and request.current_t_s - last.get("t_s", -1e9) > 5:
            return result()
        try:
            values = [last[k] for k in ("rail_hotspot_temp_c", "ambient_temp_c", "rail_current_a", "rail_voltage_v")]
            if not all(v is not None and np.isfinite(v) for v in values): return result()
            if not (-55 <= values[0] <= 125 and -55 <= values[1] <= 125 and 0 <= values[2] <= 10 and 0 <= values[3] <= 30): return result()
            if self.kind in {"ridge", "lstm", "transformer"}:
                hp = self.metadata["hyperparameters"]
                options = dict(lookback=hp["lookback_s"], step=hp["downsample_s"], gap_limit=hp["short_gap_limit_s"])
                seq, missing, invalid = sequence(obs, **options)
                quality = "degraded" if missing or invalid else "good"
                if self.kind == "ridge":
                    pred = self.model.predict(features(obs, **options)[None])[0]
                else:
                    import torch
                    norm = self.metadata["normalization"]
                    x = (seq - np.asarray(norm["mean"])) / np.asarray(norm["scale"])
                    with torch.no_grad(): pred = self.model(torch.tensor(x[None], dtype=torch.float32)).numpy()[0]
                    pred = pred * norm["y_scale"] + norm["y_mean"]
                if not np.isfinite(pred).all(): return result()
                return result(float(pred[0]), float(pred[1]), quality=quality)
            if self.kind == "persistence":
                return result(float(observed), float(observed), quality="good")
            power = last["rail_voltage_v"] * last["rail_current_a"] if last["rail_enabled"] else 0
            ambient = last["ambient_temp_c"]
            return result(temperature(observed, ambient, power, 60), temperature(observed, ambient, power, 300),
                          eta(observed, ambient, power), "good")
        except (ValueError, KeyError, TypeError):
            return result()
