import json
from pathlib import Path
import subprocess
import numpy as np
from .data import load, windows, fingerprint
from .features import FEATURE_SCHEMA
from .evaluation import score


def train(kind, data, output, seed=42, quick=False, epochs=None, config=None):
    config = config or dict(lookback_s=300, downsample_s=5, stride_s=30, short_gap_limit_s=5)
    window_options = dict(stride=config["stride_s"], lookback=config["lookback_s"], step=config["downsample_s"], gap_limit=config["short_gap_limit_s"])
    if any(type(v) is not int or v < 1 for v in window_options.values()): raise ValueError("window settings must be positive integers")
    np.random.seed(seed)
    df = load(data)
    training = windows(df, "train", quick=quick, **window_options)
    validation = windows(df, "val", quick=quick, **window_options)
    net, norm = None, None
    path = Path(output); path.mkdir(parents=True, exist_ok=True)
    if kind == "ridge":
        from .baselines import fit_ridge
        import joblib
        candidates = [(alpha, fit_ridge([w[0] for w in training], [w[2] for w in training], alpha)) for alpha in (.1, 1., 10., 100.)]
        alpha, net = min(candidates, key=lambda pair: score("ridge", validation, pair[1])["horizons"]["300"]["mae_c"])
        joblib.dump(net, path / "model.joblib")
    elif kind in {"lstm", "transformer"}:
        import torch
        from .neural import train_neural
        net, norm = train_neural(kind, training, validation, seed, epochs or (2 if quick else 20))
        torch.save(net.state_dict(), path / "weights.pt")
    validation_score = score(kind, validation, net, norm)
    persistence = score("persistence", validation)
    accepted = kind in {"rc", "persistence"} or validation_score["horizons"]["300"]["mae_c"] <= persistence["horizons"]["300"]["mae_c"]
    try: commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError): commit = None
    metadata = dict(model=kind, version="0.1.0", synthetic_only=True, seed=seed,
                    feature_schema=FEATURE_SCHEMA, rail_id_used=False, data=str(data),
                    training_data_sha256=fingerprint(data), git_commit=commit, normalization=norm,
                    validation_accepted=accepted, validation=validation_score, persistence_validation=persistence,
                    hyperparameters=dict(**config, quick=quick, ridge_alpha=alpha if kind == "ridge" else None, hidden=64, transformer_layers=2),
                    thresholds=dict(warning_c=70, critical_c=80),
                    assumptions="synthetic only; no intervention; rail ID excluded to avoid memorization")
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    return metadata


def evaluate(artifact, split="test", data=None):
    from .inference import Predictor
    path = Path(artifact)
    metadata = json.loads((path / "metadata.json").read_text())
    # Evaluate the candidate even if online validation selection chose RC fallback.
    predictor = Predictor(artifact, enforce_selection=False)
    if predictor.kind != metadata["model"]:
        raise ValueError(f"cannot evaluate candidate: {predictor.fallback_reason}")
    df = load(data or metadata["data"])
    hp = metadata["hyperparameters"]
    samples = windows(df, split, stride=hp["stride_s"], lookback=hp["lookback_s"], step=hp["downsample_s"], gap_limit=hp["short_gap_limit_s"])
    result = score(metadata["model"], samples, predictor.model, metadata.get("normalization"))
    result["persistence"] = score("persistence", samples)
    scenario_path = Path(data or metadata["data"]).with_name("model_training_scenarios.csv")
    if scenario_path.exists():
        import pandas as pd
        types = pd.read_csv(scenario_path).set_index("scenario_id").scenario_type.to_dict()
        result["per_scenario_type"] = {kind: score(metadata["model"], [w for w in samples if types[w[3]["scenario_id"]] == kind],
                                                        predictor.model, metadata.get("normalization"))
                                       for kind in sorted({types[w[3]["scenario_id"]] for w in samples})}
    (path / f"metrics-{split}.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result
