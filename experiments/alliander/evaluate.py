"""Offline Alliander compatibility experiment; never sends hardware commands."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from transformer_thermal_model.model import Model
from transformer_thermal_model.schemas import InputProfile, UserTransformerSpecifications
from transformer_thermal_model.schemas.thermal_model.initial_state import InitialTopOilTemp
from transformer_thermal_model.transformer import DistributionTransformer

HORIZONS = (60, 300)
KEYS = ["scenario_id", "rail_id", "elapsed_s"]
INPUTS = ["ambient_temp_c", "rail_current_a", "rail_hotspot_temp_c"]
TARGETS = [f"target_hotspot_temp_plus_{h}s_c" for h in HORIZONS]
ROOT = Path(__file__).resolve().parents[2]


def load_data(directory):
    """Reject ambiguous episodes/splits; retain blanks for horizon-specific filtering."""
    data = pd.read_csv(directory / "model_training_timeseries.csv")
    scenarios = pd.read_csv(directory / "model_training_scenarios.csv")
    required = KEYS + INPUTS + TARGETS + ["data_split", "sensor_valid"]
    if missing := set(required) - set(data.columns):
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if data[KEYS + ["data_split", "sensor_valid"]].isna().any().any():
        raise ValueError("Missing episode keys, splits or sensor flags")
    if data.duplicated(KEYS).any() or scenarios.scenario_id.duplicated().any():
        raise ValueError("Duplicate episode rows or scenario definitions")
    if not data.sensor_valid.isin([0, 1]).all():
        raise ValueError("sensor_valid must be 0 or 1")
    if set(data.data_split) != {"train", "val", "test"}:
        raise ValueError("Expected train, val and test splits")
    if (data.groupby("scenario_id").data_split.nunique() != 1).any():
        raise ValueError("A scenario occurs in multiple splits")
    expected = scenarios.set_index("scenario_id").data_split
    if not data.data_split.eq(data.scenario_id.map(expected)).all():
        raise ValueError("Timeseries splits disagree with scenario definitions")
    if set(data.scenario_id) != set(scenarios.scenario_id):
        raise ValueError("Scenario files do not describe the same episodes")
    numeric = data[INPUTS + TARGETS + ["elapsed_s"]].to_numpy(dtype=float)
    if np.isinf(numeric).any():
        raise ValueError("Infinite input or target")
    if (data.elapsed_s < 0).any() or (data.elapsed_s % 1 != 0).any():
        raise ValueError("elapsed_s must be nonnegative whole seconds")
    valid = data.sensor_valid.eq(1)
    if data.loc[valid, INPUTS].isna().any().any():
        raise ValueError("A supposedly valid sensor row has missing inputs")
    if (data.loc[valid, "rail_current_a"] < 0).any():
        raise ValueError("Negative current is unsupported by this demo adapter")
    data = data.merge(scenarios[["scenario_id", "scenario_type"]], on="scenario_id", validate="many_to_one")
    return data.sort_values(KEYS).reset_index(drop=True), scenarios


def make_transformer(tau_minutes, rise_c):
    # These are illustrative demo specifications, not measured transformer ratings.
    return DistributionTransformer(user_specs=UserTransformerSpecifications(
        load_loss=12.0, no_load_loss=0.1, nom_load_sec_side=1.0,
        amb_temp_surcharge=0.0, time_const_oil=tau_minutes,
        top_oil_temp_rise=rise_c, time_const_windings=1.0,
        winding_oil_gradient=5.0, hot_spot_fac=1.0,
    ))


def forecast(current_a, ambient_c, hotspot_c, transformer, offsets=(0, 60, 300)):
    """Only present readings enter; future load and ambient are held constant."""
    index = pd.Timestamp("2000-01-01") + pd.to_timedelta(offsets, unit="s")
    profile = InputProfile.create(
        datetime_index=index,
        load_profile=[current_a] * len(index),
        ambient_temperature_profile=[ambient_c] * len(index),
    )
    # shortcut: use the measured hotspot as initial oil temperature; replace with
    # a calibrated state estimator when real oil/winding measurements exist.
    output = Model(
        temperature_profile=profile, transformer=transformer,
        initial_condition=InitialTopOilTemp(initial_top_oil_temp=hotspot_c),
    ).run()
    return output.hot_spot_temp_profile.to_numpy()[1:]


def sample_origins(data, stride):
    return data.loc[
        data.sensor_valid.eq(1) & data.elapsed_s.mod(stride).eq(0)
        & data[TARGETS].notna().any(axis=1)
    ].copy()


def predict(origins, parameters):
    predictions, latencies = [], []
    transformers = {rail: make_transformer(p["tau_minutes"], p["rise_c"])
                    for rail, p in parameters.items()}
    for row in origins.itertuples(index=False):
        start = perf_counter()
        values = forecast(row.rail_current_a, row.ambient_temp_c,
                          row.rail_hotspot_temp_c, transformers[row.rail_id])
        latencies.append((perf_counter() - start) * 1000)
        predictions.append(values)
    return np.asarray(predictions), np.asarray(latencies)


def errors(origins, predictions):
    target = origins[TARGETS].to_numpy(dtype=float)
    error = predictions - target
    available = np.isfinite(target)
    return float(np.mean(error[available] ** 2)), float(np.mean(np.abs(error[available])))


def calibrate(train, validation):
    """Fit rise on train, select time constant on validation; test is not accepted."""
    if set(train.data_split) != {"train"} or set(validation.data_split) != {"val"}:
        raise ValueError("Calibration accepts train and val scenarios only")
    if set(train.scenario_id) & set(validation.scenario_id):
        raise ValueError("Calibration scenarios overlap")
    chosen, candidates = {}, []
    for rail in sorted(train.rail_id.unique()):
        rail_train = train.loc[train.rail_id.eq(rail)]
        rail_val = validation.loc[validation.rail_id.eq(rail)]
        if rail_train.empty or rail_val.empty:
            raise ValueError(f"Missing calibration split for {rail}")
        for tau in (2.0, 5.0, 10.0):
            trials = []
            for rise in (10.0, 20.0, 30.0):
                params = {rail: {"tau_minutes": tau, "rise_c": rise}}
                prediction, _ = predict(rail_train, params)
                mse, mae = errors(rail_train, prediction)
                trials.append({**params[rail], "train_mse_c2": mse, "train_mae_c": mae})
            fitted = min(trials, key=lambda p: p["train_mse_c2"])
            prediction, _ = predict(rail_val, {rail: fitted})
            _, val_mae = errors(rail_val, prediction)
            candidates.append({"rail_id": rail, **fitted, "val_mae_c": val_mae, "rise_trials": trials})
            print(f"{rail}: tau={tau:g} min, train-fit rise={fitted['rise_c']:g} C, validation MAE={val_mae:.3f} C", flush=True)
        best = min((c for c in candidates if c["rail_id"] == rail), key=lambda p: p["val_mae_c"])
        chosen[rail] = {key: best[key] for key in ("tau_minutes", "rise_c")}
    return chosen, candidates


def prediction_table(origins, predictions):
    frames = []
    for i, horizon in enumerate(HORIZONS):
        frame = origins[KEYS + ["data_split", "scenario_type", "rail_hotspot_temp_c", TARGETS[i]]].copy()
        frame = frame.rename(columns={TARGETS[i]: "actual_c", "rail_hotspot_temp_c": "persistence_c"})
        frame["horizon_s"] = horizon
        frame["alliander_c"] = predictions[:, i]
        frames.append(frame.loc[frame.actual_c.notna()])
    result = pd.concat(frames, ignore_index=True)
    if not np.isfinite(result[["actual_c", "persistence_c", "alliander_c"]].to_numpy()).all():
        raise ValueError("Non-finite scored prediction")
    return result


def score(table, groups):
    records = []
    for keys, frame in table.groupby(groups):
        for model in ("alliander", "persistence"):
            error = frame[f"{model}_c"] - frame.actual_c
            records.append({**dict(zip(groups, keys)), "model": model, "n": len(frame),
                            "mae_c": float(error.abs().mean()),
                            "rmse_c": float(np.sqrt((error ** 2).mean())),
                            "bias_c": float(error.mean()),
                            "p95_absolute_error_c": float(error.abs().quantile(.95))})
    return records


def plot_results(table, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    test = table.loc[table.data_split.eq("test")]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for ax, horizon in zip(axes, HORIZONS):
        frame = test.loc[test.horizon_s.eq(horizon)]
        for label, color in [("persistence", "#9ca3af"), ("alliander", "#1565c0")]:
            error = (frame[f"{label}_c"] - frame.actual_c).abs()
            ax.scatter(frame.actual_c, error, s=9, alpha=.35, label=f"{label}: MAE {error.mean():.2f} C", color=color)
        ax.set(title=f"{horizon}-second forecast | {len(frame):,} predictions",
               xlabel="True future temperature (C)", ylabel="Absolute forecast error (C)")
        ax.grid(alpha=.15)
        ax.legend()
    fig.suptitle("Alliander on held-out synthetic ESP32 scenarios\n30-second forecast cadence; current load and ambient held constant", fontsize=13)
    fig.savefig(output / "forecast_errors.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw/entropy_mock")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/alliander")
    args = parser.parse_args()
    started = perf_counter()
    data, scenarios = load_data(args.data_dir)
    train = sample_origins(data.loc[data.data_split.eq("train")], 60)
    validation = sample_origins(data.loc[data.data_split.eq("val")], 30)
    params, candidates = calibrate(train, validation)
    calibration_s = perf_counter() - started
    # Freeze all choices before evaluating held-out scenarios.
    origins = sample_origins(data, 30)
    predictions, latencies = predict(origins, params)
    table = prediction_table(origins, predictions)
    metrics = score(table, ["data_split", "horizon_s"])
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "predictions.csv", index=False)
    pd.DataFrame(metrics).to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(score(table, ["data_split", "scenario_id", "rail_id", "horizon_s"])).to_csv(output / "per_episode_metrics.csv", index=False)
    plot_results(table, output)
    report = {
        "model": "Alliander DistributionTransformer, illustrative demo parameters",
        "package_version": importlib.metadata.version("transformer-thermal-model"),
        "selected_parameters": params, "calibration_candidates": candidates,
        "effective_specifications": {rail: make_transformer(p["tau_minutes"], p["rise_c"]).specs.model_dump()
                                     for rail, p in params.items()},
        "forecast_assumption": "Current load and ambient remain constant; hotspot proxies initial oil temperature.",
        "data_audit": {"rows": len(data), "invalid_sensor_rows": int(data.sensor_valid.eq(0).sum()),
                       "scenario_counts": scenarios.data_split.value_counts().to_dict(),
                       "train_calibration_origins": len(train), "validation_selection_origins": len(validation),
                       "scored_forecast_origins": len(origins), "stride_s": 30,
                       "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in sorted(args.data_dir.glob("*.csv"))}},
        "metrics": metrics,
        "efficiency": {"calibration_and_load_s": calibration_s,
                       "two_horizon_forecasts_timed": len(latencies),
                       "median_ms_per_rail_two_horizons": float(np.median(latencies)),
                       "p95_ms_per_rail_two_horizons": float(np.quantile(latencies, .95)),
                       "scope": "Laptop Python forecast including profile construction; excludes CSV, plotting, hardware I/O and transformer construction."},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "packages": {name: importlib.metadata.version(name)
                                     for name in ["transformer-thermal-model", "numpy", "pandas", "pydantic", "matplotlib"]}},
        "limitations": ["All sensor data and targets are synthetic RC simulations.",
                        "No actual transformer geometry, ratings or thermal calibration available.",
                        "Illustrative 12 W load loss, 0.1 W no-load loss, 1 A nominal load; not inferred from hardware.",
                        "Hotspot-as-oil initial state and 5 C winding gradient are proxy assumptions.",
                        "Overlapping forecast windows are correlated; counts are not independent trials.",
                        "Future load changes are unknown; no PID or relay policy tested.",
                        "Laptop timing does not establish ESP32 runtime or memory feasibility."],
    }
    (output / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(pd.DataFrame(metrics).to_string(index=False))
    print(json.dumps(report["efficiency"], indent=2))
    print(f"Saved results to {output}")


if __name__ == "__main__":
    main()
