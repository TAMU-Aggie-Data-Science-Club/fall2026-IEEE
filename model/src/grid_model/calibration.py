"""Fit RC R/tau to training observations only; provenance is mandatory."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from .data import load, fingerprint
from .thermal_rc import temperature


def calibrate(data, output):
    df = load(data)
    train = df[df.data_split == "train"]
    result = dict(hardware_domain="demo_rc", provenance="fitted supplied synthetic training measurements only; NOT physical calibration",
                  physical_calibration_verified=False, data_sha256=fingerprint(data), rails={})
    for rail, rows in train.groupby("rail_id"):
        pairs = []
        for _, group in rows.groupby("scenario_id"):
            sampled = group.iloc[::10]
            records = sampled.to_dict("records")
            for a, b in zip(records, records[1:]):
                if a["sensor_valid"] and b["sensor_valid"]:
                    pairs.append([a["rail_hotspot_temp_c"], a["ambient_temp_c"], a["rail_power_w"],
                                  b["elapsed_s"]-a["elapsed_s"], b["rail_hotspot_temp_c"]])
        values = np.asarray(pairs)
        def residual(x):
            eq = values[:, 1] + x[0]*values[:, 2]
            return eq+(values[:, 0]-eq)*np.exp(-values[:, 3]/x[1])-values[:, 4]
        fitted = least_squares(residual, [3.2, 300.], bounds=([.05, 10.], [20., 10000.]))
        result["rails"][rail] = dict(resistance_c_per_w=float(fitted.x[0]), tau_s=float(fitted.x[1]),
                                      training_step_mae_c=float(np.abs(residual(fitted.x)).mean()))
    path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result
