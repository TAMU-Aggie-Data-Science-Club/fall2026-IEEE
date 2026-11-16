"""Compare hotspot forecasters on the synthetic ESP32 scenarios; offline, no hardware commands."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.optimize import least_squares

HORIZONS = (60, 300)
KEYS = ["scenario_id", "rail_id", "elapsed_s"]
EPISODE = ["scenario_id", "rail_id"]
TARGETS = [f"target_hotspot_temp_plus_{h}s_c" for h in HORIZONS]
ROOT = Path(__file__).resolve().parents[2]
FOLDS = 5
STEP_W = 5.0  # a load step is a >5 W jump of the 5 s mean power over the preceding 30 s mean
LAGS = (30, 60, 120, 300)
FEATURES = (["A", "T_m5", "gap", "rail", "P_base", "since_up", "since_dn", "n_up", "n_dn"]
            + [f"P_m{w}" for w in (5, 15, 30, 60, 120, 300)]
            + [f"{v}_d{w}" for v in "TP" for w in LAGS])
XGB = dict(n_estimators=500, learning_rate=.03, max_depth=4, subsample=.8, colsample_bytree=.8,
           min_child_weight=20, objective="reg:absoluteerror", random_state=0)


def load_data(directory):
    data = pd.read_csv(directory / "model_training_timeseries.csv")
    scenarios = pd.read_csv(directory / "model_training_scenarios.csv").set_index("scenario_id")
    if data.duplicated(KEYS).any():
        raise ValueError("Duplicate episode rows")
    if not data.data_split.eq(data.scenario_id.map(scenarios.data_split)).all():
        raise ValueError("Timeseries splits disagree with scenario definitions")
    data["scenario_type"] = data.scenario_id.map(scenarios.scenario_type)
    return data.sort_values(KEYS).reset_index(drop=True)


def step_clock(power):
    """Seconds since the last upward/downward load step and how many of each were seen so far."""
    power = pd.Series(power)
    jump = (power.rolling(5, min_periods=1).mean()
            - power.shift(5).rolling(30, min_periods=1).mean()).fillna(0).to_numpy()
    out = np.zeros((len(jump), 4))
    since_up = since_dn = 1800.0  # "never", capped at one episode length
    n_up = n_dn = lockout = 0
    for i, j in enumerate(jump):
        since_up, since_dn = min(since_up + 1, 1800.0), min(since_dn + 1, 1800.0)
        if lockout:
            lockout -= 1  # one physical step stays above threshold for ~35 s; count it once
        elif j > STEP_W:
            since_up, n_up, lockout = 0.0, n_up + 1, 40
        elif j < -STEP_W:
            since_dn, n_dn, lockout = 0.0, n_dn + 1, 40
        out[i] = since_up, since_dn, n_up, n_dn
    return out


def add_features(data):
    """Each feature row uses readings at or before that row only; gaps keep the last reading."""
    data = data.copy()
    group = data.groupby(EPISODE, sort=False)
    data["A"] = data.ambient_temp_c
    data["T"] = group.rail_hotspot_temp_c.ffill()
    data["P"] = group.rail_power_w.ffill()
    group = data.groupby(EPISODE, sort=False)

    def mean(column, window):
        return group[column].transform(lambda s: s.rolling(window, min_periods=1).mean())

    data["T_m5"] = mean("T", 5)
    for window in (5, 15, 30, 60, 120, 300):
        data[f"P_m{window}"] = mean("P", window)
    group = data.groupby(EPISODE, sort=False)
    for lag in LAGS:  # blank until that much history exists; xgboost handles blanks natively
        data[f"T_d{lag}"] = data.T_m5 - group.T_m5.shift(lag)
        data[f"P_d{lag}"] = data.P_m15 - group.P_m15.shift(lag)
    data["P_base"] = group.P.cummin()
    data[["since_up", "since_dn", "n_up", "n_dn"]] = np.vstack(
        [step_clock(frame.P) for _, frame in group])
    data["rail"] = data.rail_id.str[-1].astype(int)
    return data


def rc_forecast(frame, params, horizon):
    """First-order RC with load and ambient held at their current readings."""
    tau = frame.rail.map(lambda r: params[r][0])
    resistance = frame.rail.map(lambda r: params[r][1])
    decay = np.exp(-horizon / tau)
    return ((frame.A + resistance * frame.P_m5) * (1 - decay) + frame.T_m5 * decay).to_numpy()


def fit_rc(train):
    """Per-rail time constant (s) and thermal resistance (C/W); robust loss because
    windows that contain an unforeseeable load step would otherwise drag the fit."""
    params = {}
    for rail, frame in train.groupby("rail"):
        def residual(p):
            return np.nan_to_num(np.concatenate(
                [rc_forecast(frame, {rail: p}, h) - frame[t] for h, t in zip(HORIZONS, TARGETS)]))
        params[int(rail)] = least_squares(residual, [400.0, 3.0], loss="soft_l1").x.tolist()
    return params


def fit_predict(train, origins):
    """Return {model: (n_origins, n_horizons)} plus the fitted pieces for timing/reporting."""
    train = train.loc[train.elapsed_s.mod(5).eq(0)]
    params = fit_rc(train)
    shape = (len(origins), len(HORIZONS))
    out = {name: np.empty(shape) for name in ("persistence", "rc", "xgb", "xgb_clock")}
    models = {}
    for i, (horizon, target) in enumerate(zip(HORIZONS, TARGETS)):
        fit = train.loc[train[target].notna()].assign(gap=lambda f: rc_forecast(f, params, horizon) - f.T_m5)
        score = origins.assign(gap=lambda f: rc_forecast(f, params, horizon) - f.T_m5)
        out["persistence"][:, i] = score["T"]
        out["rc"][:, i] = score.T_m5 + score.gap
        # xgb_clock also sees elapsed_s: it may memorise the generator's scripted event times.
        for name, columns in (("xgb", FEATURES), ("xgb_clock", FEATURES + ["elapsed_s"])):
            model = xgb.XGBRegressor(**XGB).fit(fit[columns], fit[target] - fit.T_m5)
            out[name][:, i] = score.T_m5 + model.predict(score[columns])
            models[name, horizon] = model
    return out, params, models


def gru_predict(data, train, origins, params, seeds=3, epochs=25):
    """GRU over the last 300 s (5 s steps) that corrects the RC forecast; mean of `seeds` runs
    because single runs differ by ~0.2 C at 300 s."""
    import torch  # heavy and optional: only imported for --gru
    from torch import nn

    T, P, A, elapsed = (data[c].to_numpy() for c in ("T", "P", "A", "elapsed_s"))

    def inputs(frame):
        i = frame.index.to_numpy()  # data has a positional index, sorted by episode then time
        j = i[:, None] + np.arange(-295, 1, 5)
        start = (i - elapsed[i])[:, None]
        seen = j >= start
        j = np.maximum(j, start)  # before the episode began: repeat its first reading
        sequence = np.stack([(T[j] - T[i, None]) / 5, (P[j] - 8) / 6, A[j] - A[i, None], seen], -1)
        base = np.column_stack([rc_forecast(frame, params, h) for h in HORIZONS])
        static = np.column_stack([(frame.T_m5 - frame.A) / 20, (frame.P_m5 - 8) / 6,
                                  (base - frame.T_m5.to_numpy()[:, None]) / 10,
                                  frame.rail.to_numpy()[:, None] == [1, 2, 3],
                                  frame[["since_up", "since_dn"]] / 600, frame[["n_up", "n_dn"]]])
        as_tensor = lambda a: torch.tensor(np.nan_to_num(a.astype(np.float32)))
        return as_tensor(sequence), as_tensor(static), base

    class Net(nn.Module):
        def __init__(self, n_static):
            super().__init__()
            self.gru = nn.GRU(4, 48, batch_first=True)
            self.head = nn.Sequential(nn.Linear(48 + n_static, 64), nn.ReLU(), nn.Linear(64, len(HORIZONS)))

        def forward(self, sequence, static):
            return self.head(torch.cat([self.gru(sequence)[1][0], static], 1))

    train = train.loc[train.elapsed_s.mod(5).eq(0)]
    x, static, base = inputs(train)
    y = torch.tensor((train[TARGETS].to_numpy() - base).astype(np.float32))
    known, y = ~torch.isnan(y), torch.nan_to_num(y)
    x_new, static_new, base_new = inputs(origins)
    correction = np.zeros_like(base_new)
    for seed in range(seeds):
        torch.manual_seed(seed)
        net = Net(static.shape[1])
        optimiser = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-3)
        schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, 4e-3, total_steps=epochs * (len(x) // 256 + 1))
        for _ in range(epochs):
            for batch in torch.randperm(len(x)).split(256):
                loss = nn.functional.smooth_l1_loss(net(x[batch], static[batch]), y[batch], reduction="none", beta=.5)
                loss = (loss * known[batch]).sum() / known[batch].sum()  # blank horizons carry no loss
                optimiser.zero_grad()
                loss.backward()
                optimiser.step()
                schedule.step()
        with torch.no_grad():
            correction += net.eval()(x_new, static_new).numpy() / seeds
    return base_new + correction


def long_table(origins, predictions, evaluation):
    frames = []
    for i, (horizon, target) in enumerate(zip(HORIZONS, TARGETS)):
        frame = origins[KEYS + ["data_split", "scenario_type", f"step_in_{horizon}s"]].rename(
            columns={f"step_in_{horizon}s": "load_step_in_horizon"})
        frame = frame.assign(evaluation=evaluation, horizon_s=horizon, actual_c=origins[target],
                             **{name: p[:, i] for name, p in predictions.items()})
        frames.append(frame.loc[frame.actual_c.notna()])
    return pd.concat(frames, ignore_index=True)


def score(table, groups, models):
    records = []
    for keys, frame in table.groupby(groups):
        for model in models:
            if frame[model].isna().all():
                continue  # Alliander has no cross-validated forecasts
            error = frame[model] - frame.actual_c
            records.append({**dict(zip(groups, keys)), "model": model, "n": len(frame),
                            "mae_c": error.abs().mean(), "rmse_c": np.sqrt((error ** 2).mean()),
                            "bias_c": error.mean(), "p95_absolute_error_c": error.abs().quantile(.95)})
    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw/entropy_mock")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/model_comparison")
    parser.add_argument("--alliander", type=Path, default=ROOT / "data/processed/alliander/predictions.csv")
    parser.add_argument("--gru", action="store_true", help="also train the GRU (needs torch, ~15 min)")
    args = parser.parse_args()
    data = add_features(load_data(args.data_dir))
    group = data.groupby(EPISODE, sort=False)
    for horizon in HORIZONS:  # label for analysis only, never a feature: does the load step inside the window?
        data[f"step_in_{horizon}s"] = (group.P_m15.shift(-horizon) - data.P_m15).abs() > STEP_W
    data["fold"] = data.scenario_id.str[1:].astype(int) % FOLDS
    valid = data.loc[data.sensor_valid.eq(1)]
    develop = valid.loc[valid.data_split.ne("test")]  # train + val; test never enters fitting or selection
    origins = valid.loc[valid.elapsed_s.mod(30).eq(0) & valid[TARGETS].notna().any(axis=1)]

    tables = []
    for fold in range(FOLDS):  # whole scenarios are held out together
        held = origins.loc[origins.data_split.ne("test") & origins.fold.eq(fold)]
        train = develop.loc[develop.fold.ne(fold)]
        predictions, fold_params, _ = fit_predict(train, held)
        if args.gru:
            predictions["gru"] = gru_predict(data, train, held, fold_params)
        tables.append(long_table(held, predictions, "cv"))
        print(f"fold {fold + 1}/{FOLDS} done", flush=True)
    test = origins.loc[origins.data_split.eq("test")]
    predictions, params, models = fit_predict(develop, test)
    if args.gru:
        predictions["gru"] = gru_predict(data, develop, test, params)
    table = pd.concat(tables + [long_table(test, predictions, "test")], ignore_index=True)
    names = list(predictions)
    if args.alliander.exists():  # same held-out rows, so the earlier experiment is directly comparable
        earlier = pd.read_csv(args.alliander).query("data_split == 'test'")
        table = table.merge(earlier[KEYS + ["horizon_s", "alliander_c"]].rename(columns={"alliander_c": "alliander"}),
                            on=KEYS + ["horizon_s"], how="left", validate="one_to_one")
        if table.loc[table.evaluation.eq("test"), "alliander"].isna().any():
            raise ValueError("Alliander predictions do not cover the same test rows")
        names.append("alliander")

    row = test.iloc[[0]]
    start = perf_counter()
    for _ in range(200):
        for horizon in HORIZONS:
            models["xgb", horizon].predict(row.assign(gap=0.0)[FEATURES])
    latency_ms = (perf_counter() - start) / 200 * 1000

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "predictions.csv", index=False)
    metrics = score(table, ["evaluation", "horizon_s"], names)
    metrics.to_csv(output / "metrics.csv", index=False)
    score(table, ["evaluation", "horizon_s", "scenario_type"], names).to_csv(output / "per_type_metrics.csv", index=False)
    by_step = score(table, ["evaluation", "horizon_s", "load_step_in_horizon"], names)
    by_step.to_csv(output / "load_step_metrics.csv", index=False)
    (output / "results.json").write_text(json.dumps({
        "rc_parameters_tau_s_and_r_c_per_w": params, "xgboost": XGB, "features": FEATURES,
        "selection": f"{FOLDS}-fold scenario-grouped CV on train+val; final fit on train+val; test scored once",
        "xgb_two_horizon_latency_ms": latency_ms, "metrics": metrics.to_dict("records"),
    }, indent=2) + "\n")
    wide = metrics.pivot(index="model", columns=["evaluation", "horizon_s"], values="mae_c")
    print("\nMAE (C)\n" + wide.sort_values(("cv", 300)).round(3).to_string())
    print("\nTest MAE (C) with / without a load step inside the horizon\n" + by_step.query("evaluation == 'test'").pivot(
        index="model", columns=["horizon_s", "load_step_in_horizon"], values="mae_c").round(3).to_string())
    print(f"\nRC parameters {params}\nxgb latency {latency_ms:.2f} ms per rail for both horizons\nSaved to {output}")


if __name__ == "__main__":
    main()
