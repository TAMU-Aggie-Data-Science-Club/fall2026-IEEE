"""One causal transformation shared by batch training and online inference."""
import numpy as np
import pandas as pd

CHANNELS = ["rail_hotspot_temp_c", "rail_current_a", "rail_voltage_v",
            "ambient_temp_c", "rail_enabled"]
FEATURE_SCHEMA = [f"{c}_{s}" for c in CHANNELS for s in ("last", "mean", "min", "max")] + ["temp_rate", "missing_fraction", "invalid_fraction", "power_last", "power_mean", "rc_60", "rc_300"]


def sequence(observations: list[dict], lookback=300, step=5, gap_limit=5):
    if lookback < 2 or step < 1 or lookback % step:
        raise ValueError("lookback must be divisible by downsample interval")
    df = pd.DataFrame(observations).sort_values("t_s")
    if df.empty or df.t_s.duplicated().any():
        raise ValueError("empty/duplicate observation times")
    end = float(df.t_s.iloc[-1])
    if end - float(df.t_s.iloc[0]) < lookback - 1:
        raise ValueError("insufficient history")
    df = df[df.t_s > end - lookback].set_index("t_s")
    # Reindex at 1 Hz: missing packets are explicit, never interpolated from future.
    df = df.reindex(np.arange(end - lookback + 1, end + 1))
    values = df[CHANNELS].astype(float)
    bad = df.sensor_valid.ne(True)
    values.loc[bad, CHANNELS[:3]] = np.nan
    missing = values.isna().mean().mean()
    values = values.ffill(limit=gap_limit)
    if values.isna().any().any() or missing > .1:
        raise ValueError("long sensor gap")
    sampled = values.iloc[step - 1::step].to_numpy(dtype=np.float32)
    mask = df[CHANNELS].isna().astype(float).iloc[step - 1::step].to_numpy(dtype=np.float32)
    quality = df.sensor_valid.fillna(False).astype(float).iloc[step - 1::step].to_numpy(dtype=np.float32)[:, None]
    return np.concatenate([sampled, mask, quality], axis=1), float(missing), float(bad.mean())


def features(observations, lookback=300, step=5, gap_limit=5):
    from .thermal_rc import temperature
    seq, missing, invalid = sequence(observations, lookback, step, gap_limit)
    x = seq[:, :5]
    stats = [v for col in x.T for v in (col[-1], col.mean(), col.min(), col.max())]
    power = x[:, 1] * x[:, 2] * x[:, 4]
    rc = [temperature(x[-1, 0], x[-1, 3], power[-1], h) for h in (60, 300)]
    return np.asarray(stats + [(x[-1, 0] - x[0, 0]) / max(step, lookback - step), missing, invalid,
                               power[-1], power.mean(), *rc], dtype=np.float32)
