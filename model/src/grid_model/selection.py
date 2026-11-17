"""Explicit model family selection; oil models never silently fall back to RC."""
import json
from pathlib import Path
from .inference import Predictor
from .physics_ieee import TransformerParameters
from .transformer_predictor import TransformerPredictor


def select_model(model="calibrated_rc", artifact=None, parameters=None, calibration=None):
    if model in {"ieee_c57_91", "alliander_iec"}:
        params = TransformerParameters(**json.loads(Path(parameters).read_text())) if isinstance(parameters, (str, Path)) else parameters
        return TransformerPredictor(model, params)
    if model == "ridge":
        return Predictor(artifact or "model/artifacts/ridge-demo")
    if model not in {"rc", "calibrated_rc", "persistence"}: raise ValueError("unknown model")
    predictor = Predictor(model="rc" if model == "calibrated_rc" else model)
    predictor.kind = model
    predictor.rc_calibration = json.loads(Path(calibration).read_text()) if calibration else None
    return predictor
