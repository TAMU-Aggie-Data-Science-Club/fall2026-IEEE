from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from .features import features, sequence

TARGETS = ["target_hotspot_temp_plus_60s_c", "target_hotspot_temp_plus_300s_c"]
HEADERS = ("scenario_id,data_split,timestamp_utc,elapsed_s,rail_id,ambient_temp_c,bus_voltage_v,"
           "rail_voltage_v,rail_current_a,rail_power_w,rail_hotspot_temp_c,rail_enabled,sensor_valid,"
           "target_hotspot_temp_plus_60s_c,target_hotspot_temp_plus_300s_c,"
           "target_crosses_80c_next_300s,target_time_to_80c_within_600s").split(",")
DEFAULT_DATA = "model/data/model_training_timeseries.csv"


def load(path=DEFAULT_DATA, scenarios=None):
    if not Path(path).is_file():
        raise ValueError(f"Missing fixture {path}; copy supplied synthetic package into model/data/")
    df = pd.read_csv(path)
    if list(df.columns) != HEADERS:
        raise ValueError("training CSV headers do not match contract")
    for column in HEADERS[3:]:
        if column != "rail_id": df[column] = pd.to_numeric(df[column], errors="raise")
    if df[["scenario_id", "data_split", "rail_id", "timestamp_utc", "elapsed_s", "ambient_temp_c", "bus_voltage_v", "rail_enabled", "sensor_valid"]].isna().any().any():
        raise ValueError("missing required metadata/environment")
    if (df.elapsed_s < 0).any() or (df.elapsed_s % 1 != 0).any():
        raise ValueError("elapsed time must be nonnegative integer seconds")
    for column, low, high in [("ambient_temp_c", -55, 125), ("rail_hotspot_temp_c", -55, 125),
                               ("bus_voltage_v", 0, 30), ("rail_voltage_v", 0, 30),
                               ("rail_current_a", 0, 10), ("rail_power_w", 0, 300)]:
        if not df[column].dropna().between(low, high).all(): raise ValueError(f"out of range: {column}")
    if df.loc[df.sensor_valid == 1, ["rail_hotspot_temp_c", "rail_voltage_v", "rail_current_a", "rail_power_w"]].isna().any().any():
        raise ValueError("valid sensor has missing observations")
    if not df.target_crosses_80c_next_300s.dropna().isin([0, 1]).all():
        raise ValueError("crossing labels must be binary or unavailable")
    eta_labels = df.target_time_to_80c_within_600s.dropna()
    if not eta_labels.between(-1, 600).all(): raise ValueError("ETA label outside bounded horizon")
    if not set(df.rail_id) <= {"rail_1", "rail_2", "rail_3"}:
        raise ValueError("unknown rail")
    if not set(df.data_split) <= {"train", "val", "test"}:
        raise ValueError("unknown split")
    if df.groupby("scenario_id").data_split.nunique().max() != 1:
        raise ValueError("scenario split leakage")
    for _, group in df.groupby(["scenario_id", "rail_id"], sort=False):
        if (group.elapsed_s.diff().dropna() <= 0).any():
            raise ValueError("nonmonotonic/duplicate elapsed time")
        for horizon, target in zip((60, 300), TARGETS):
            if group.loc[group.elapsed_s + horizon > group.elapsed_s.max(), target].notna().any():
                raise ValueError("labels without complete lookahead")
        if group.loc[group.elapsed_s + 300 > group.elapsed_s.max(), "target_crosses_80c_next_300s"].notna().any():
            raise ValueError("crossing label without full future horizon")
        if group.loc[group.elapsed_s + 600 > group.elapsed_s.max(), "target_time_to_80c_within_600s"].notna().any():
            raise ValueError("ETA label without complete lookahead")
    for column in ("sensor_valid", "rail_enabled"):
        if not df[column].isin([0, 1]).all():
            raise ValueError(f"invalid {column}")
    numeric = df.select_dtypes(include="number")
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("infinite observations")
    pd.to_datetime(df.timestamp_utc, utc=True, errors="raise")
    scenario_path = Path(scenarios) if scenarios else Path(path).with_name("model_training_scenarios.csv")
    if scenario_path.exists():
        definitions = pd.read_csv(scenario_path)
        actual = df[["scenario_id", "data_split"]].drop_duplicates().sort_values("scenario_id").reset_index(drop=True)
        expected = definitions[["scenario_id", "data_split"]].sort_values("scenario_id").reset_index(drop=True)
        if not actual.equals(expected):
            raise ValueError("scenario register mismatch")
    return df


def inspect(path=DEFAULT_DATA, scenarios=None):
    df = load(path, scenarios)
    groups = df.groupby(["scenario_id", "rail_id"])
    return {"rows": len(df), "scenarios": df.scenario_id.nunique(),
            "split_scenarios": df.drop_duplicates("scenario_id").data_split.value_counts().to_dict(),
            "missing": df.isna().sum().to_dict(),
            "gaps": int(groups.elapsed_s.diff().gt(1).sum()),
            "crossing_frequency": float(df.target_crosses_80c_next_300s.mean()),
            "synthetic_only": True}


def windows(df, split, stride=30, quick=False, lookback=300, step=5, gap_limit=5):
    selected = df[df.data_split == split]
    if quick:
        selected = selected[selected.scenario_id.isin(selected.scenario_id.unique()[:2])]
    result = []
    for (scenario, rail), group in selected.groupby(["scenario_id", "rail_id"], sort=False):
        records = group.rename(columns={"elapsed_s": "t_s"}).to_dict("records")
        for i in range(lookback - 1, len(records), stride):
            row = records[i]
            if any(pd.isna(row[k]) for k in TARGETS):
                continue
            # A causal forward-fill may repair a short historical gap, but an
            # invalid endpoint cannot be scored as an observed persistence/RC input.
            if not row["sensor_valid"] or any(pd.isna(row[k]) for k in ("rail_hotspot_temp_c", "rail_current_a", "rail_voltage_v", "ambient_temp_c", "rail_power_w")):
                continue
            history = records[max(0, i - lookback + 1):i + 1]
            try:
                x = features(history, lookback, step, gap_limit)
                seq = sequence(history, lookback, step, gap_limit)[0]
            except ValueError:
                continue
            result.append((x, seq, [row[k] for k in TARGETS], row))
    if not result:
        raise ValueError(f"no complete valid {split} windows")
    return result


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
