import time
import numpy as np
from .thermal_rc import temperature, eta
from .crossing import detection_metrics


def score(kind, windows, model=None, normalization=None):
    start = time.perf_counter()
    truth = np.asarray([w[2] for w in windows])
    current = np.asarray([w[3]["rail_hotspot_temp_c"] for w in windows])
    if kind == "ridge":
        predicted = model.predict(np.asarray([w[0] for w in windows]))
    elif kind in {"lstm", "transformer"}:
        import torch
        norm = normalization
        x = (np.asarray([w[1] for w in windows]) - norm["mean"]) / norm["scale"]
        model.eval()
        with torch.no_grad():
            predicted = np.concatenate([model(batch).numpy() for batch in torch.tensor(x, dtype=torch.float32).split(128)])
        predicted = predicted * norm["y_scale"] + norm["y_mean"]
    elif kind == "persistence":
        predicted = np.repeat(current[:, None], 2, axis=1)
    elif kind in {"rc", "calibrated_rc"}:
        def rc_options(row):
            params = (model or {}).get("rails", {}).get(row["rail_id"], {})
            return dict(resistance=params.get("resistance_c_per_w",3.2),tau=params.get("tau_s",300.))
        predicted = np.asarray([[temperature(r["rail_hotspot_temp_c"], r["ambient_temp_c"], r["rail_power_w"], h, **rc_options(r))
                                 for h in (60, 300)] for *_, r in windows])
    else:
        raise ValueError(f"unknown evaluation strategy: {kind}")
    def metrics(indices):
        delta = predicted[indices] - truth[indices]
        return {str(h): {"mae_c": float(np.abs(delta[:, j]).mean()), "rmse_c": float(np.sqrt((delta[:, j] ** 2).mean()))}
                for j, h in enumerate((60, 300))}
    actual = np.asarray([w[3]["target_crosses_80c_next_300s"] == 1 for w in windows])
    true_eta = [w[3]["target_time_to_80c_within_600s"] for w in windows]
    predicted_eta = None
    if kind in {"rc", "calibrated_rc"}:
        predicted_eta = [eta(r["rail_hotspot_temp_c"], r["ambient_temp_c"], r["rail_power_w"], horizon=300, **rc_options(r)) for *_, r in windows]
    detection = detection_metrics(current, predicted, actual, true_eta, predicted_eta=predicted_eta)
    ids = np.asarray([w[3]["scenario_id"] for w in windows])
    return {"horizons": metrics(np.ones(len(windows), dtype=bool)),
            "per_scenario": {s: metrics(ids == s) for s in sorted(set(ids))},
            "crossing": detection["all_windows"], "detection": detection,
            "prediction_sha256": __import__("hashlib").sha256(predicted.tobytes()).hexdigest(),
            "eta_mae_s": detection["crossing_time"]["mae_s"],
            "cpu_ms_per_window": (time.perf_counter() - start) * 1000 / len(windows),
            "limitations": "synthetic RC only; imbalanced crossings; regression crossing times are sparse-trajectory estimates"}
