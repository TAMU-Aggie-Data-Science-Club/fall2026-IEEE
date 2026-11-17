"""Separate validation-tuned early-warning classifier; never replaces Ridge weights."""
from pathlib import Path
import json
import hashlib
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
from .data import load, windows, fingerprint
from .evaluation import score
from .crossing import confusion
from .inference import Predictor


@threadpool_limits.wrap(limits=2)
def compare(data, ridge_artifact, output):
    df = load(data)
    groups = {split: windows(df, split) for split in ("train", "val", "test")}
    # Future-onset classifier excludes already-hot windows in fitting AND scoring.
    eligible = {split: [w for w in rows if w[3]["rail_hotspot_temp_c"] < 80] for split, rows in groups.items()}
    def xy(rows): return np.asarray([w[0] for w in rows]), np.asarray([w[3]["target_crosses_80c_next_300s"] == 1 for w in rows])
    tx, ty = xy(eligible["train"]); vx, vy = xy(eligible["val"])
    net = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=7, learning_rate=.08,
                                        l2_regularization=2., random_state=42, early_stopping=False,
                                        class_weight="balanced").fit(tx, ty)
    probabilities = net.predict_proba(vx)[:, 1]
    candidates = []
    for threshold in np.unique(np.r_[0., np.linspace(.01, .99, 99), probabilities]):
        metrics = confusion(vy, probabilities >= threshold)
        if metrics["recall"] is not None and metrics["recall"] >= .9:
            candidates.append((metrics["false_positives"], -float(threshold), threshold, metrics))
    if not candidates: raise ValueError("validation has no crossing positives; cannot tune recall")
    _, _, threshold, val_metrics = min(candidates)
    test_x, test_y = xy(eligible["test"])
    test_prob = net.predict_proba(test_x)[:, 1]
    ridge = Predictor(ridge_artifact, enforce_selection=False)
    if ridge.kind != "ridge": raise ValueError("a valid original Ridge benchmark is required")
    result = {kind: score(kind, groups["test"], ridge.model if kind == "ridge" else None) for kind in ("ridge", "persistence", "rc")}
    # A warning operating point is tuned separately from the fixed 80C forecast
    # accuracy benchmark. Neither weights nor displayed temperature predictions change.
    val_temperatures = np.max(ridge.model.predict(vx),axis=1)
    operating_points = []
    for cutoff in np.unique(np.r_[50.,val_temperatures]):
        metrics = confusion(vy,val_temperatures >= cutoff)
        if metrics["recall"] is not None and metrics["recall"] >= .9:
            operating_points.append((metrics["false_positives"],-float(cutoff),cutoff,metrics))
    _,_,warning_cutoff,warning_val = min(operating_points)
    warning_test = np.max(ridge.model.predict(test_x),axis=1)
    result["ridge_early_warning"] = dict(validation=warning_val,test_future_onset=confusion(test_y,warning_test >= warning_cutoff),
        forecast_warning_cutoff_c=float(warning_cutoff),actual_event_threshold_c=80.,
        tuning="validation-only recall>=0.90 operating point; unchanged Ridge temperatures/weights",
        limitation="early warning is distinct from physical thresholds and regression accuracy")
    calibration_file = Path("model/artifacts/rc-calibration/calibration.json")
    if calibration_file.exists():
        calibration = json.loads(calibration_file.read_text())
        if calibration.get("data_sha256") == fingerprint(data):
            result["calibrated_rc"] = score("calibrated_rc",groups["test"],calibration)
    result["early_warning_classifier"] = dict(validation=val_metrics, test_future_onset=confusion(test_y, test_prob >= threshold),
        threshold=float(threshold), tuning="minimum false positives on validation subject to recall>=0.90; test untouched",
        timing="classification gives an event warning, not a temperature or ETA", calibrated_probability=False)
    # Choose on validation, never on held-out precision/recall. This selection is
    # advisory-only until the false-alarm tradeoff has been reviewed by operators.
    result["selected_warning_strategy"] = "ridge_early_warning" if warning_val["false_positives"] <= val_metrics["false_positives"] else "early_warning_classifier"
    result["data_sha256"] = fingerprint(data)
    result["ridge_weights_sha256"] = hashlib.sha256((Path(ridge_artifact)/"model.joblib").read_bytes()).hexdigest()
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    joblib.dump(net, out/"detector.joblib")
    (out/"comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result
