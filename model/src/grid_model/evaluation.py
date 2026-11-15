import time
import numpy as np
from .thermal_rc import temperature, eta


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
    else:
        predicted = np.asarray([[temperature(r["rail_hotspot_temp_c"], r["ambient_temp_c"], r["rail_power_w"], h)
                                 for h in (60, 300)] for *_, r in windows])
    def metrics(indices):
        delta = predicted[indices] - truth[indices]
        return {str(h): {"mae_c": float(np.abs(delta[:, j]).mean()), "rmse_c": float(np.sqrt((delta[:, j] ** 2).mean()))}
                for j, h in enumerate((60, 300))}
    actual = np.asarray([w[3]["target_crosses_80c_next_300s"] == 1 for w in windows])
    estimated = np.maximum(current, predicted[:, 1]) >= 80
    tp = int((actual & estimated).sum())
    eta_errors = []
    if kind == "rc":
        for *_, r in windows:
            e = eta(r["rail_hotspot_temp_c"], r["ambient_temp_c"], r["rail_power_w"])
            label = r["target_time_to_80c_within_600s"]
            if e is not None and np.isfinite(label) and label >= 0: eta_errors.append(abs(e-label))
    ids = np.asarray([w[3]["scenario_id"] for w in windows])
    return {"horizons": metrics(np.ones(len(windows), dtype=bool)),
            "per_scenario": {s: metrics(ids == s) for s in sorted(set(ids))},
            "crossing": {"precision": tp / int(estimated.sum()) if estimated.any() else None,
                         "recall": tp / int(actual.sum()) if actual.any() else None,
                         "positive_count": int(actual.sum()), "count": len(windows),
                         "method": "endpoint/current threshold proxy; can miss intermediate crossings"},
            "eta_mae_s": float(np.mean(eta_errors)) if eta_errors else None,
            "cpu_ms_per_window": (time.perf_counter() - start) * 1000 / len(windows),
            "limitations": "synthetic RC only; imbalanced crossings; uncertainty uncalibrated; ETA only RC trajectory"}
