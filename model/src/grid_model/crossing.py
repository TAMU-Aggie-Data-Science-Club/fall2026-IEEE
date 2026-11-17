"""Detection metrics are independent of temperature regression loss."""
import numpy as np


def first_crossing(times, temperatures, threshold):
    times, values = np.asarray(times, float), np.asarray(temperatures, float)
    if times.ndim != 1 or values.shape != times.shape or len(times) == 0 or not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError("finite equal 1-D trajectory arrays required")
    if (np.diff(times) <= 0).any() or not np.isfinite(threshold): raise ValueError("invalid crossing time/threshold")
    indices = np.flatnonzero(values >= threshold)
    if not len(indices): return None
    i = indices[0]
    if i == 0: return float(times[0])
    return float(times[i-1] + (times[i]-times[i-1])*(threshold-values[i-1])/(values[i]-values[i-1]))


def confusion(actual, detected):
    actual, detected = np.asarray(actual, bool), np.asarray(detected, bool)
    if actual.shape != detected.shape: raise ValueError("detection shape mismatch")
    tp, fp = int((actual & detected).sum()), int((~actual & detected).sum())
    fn, tn = int((actual & ~detected).sum()), int((~actual & ~detected).sum())
    return dict(precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None,
                true_positives=tp, false_positives=fp, false_negatives=fn, true_negatives=tn,
                positive_count=int(actual.sum()), count=int(actual.size))


def detection_metrics(current, predictions, labels, true_eta=None, threshold=80., predicted_eta=None):
    current, predictions, labels = np.asarray(current), np.asarray(predictions), np.asarray(labels, bool)
    if current.ndim != 1 or predictions.shape != (len(current),2) or labels.shape != current.shape or not np.isfinite(current).all() or not np.isfinite(predictions).all():
        raise ValueError("finite current and two-horizon predictions of matching shape required")
    # Each row uses THIS candidate's own +60/+300 outputs. The maximum includes
    # the +60 point, detecting a predicted peak even when +300 has cooled again.
    detected = np.maximum(current, np.max(predictions, axis=1)) >= threshold
    if predicted_eta is not None:
        # A real physics trajectory supersedes sparse endpoints: an IEC transient
        # can peak between 60s and 300s even when both endpoint values are lower.
        if len(predicted_eta) != len(current): raise ValueError("trajectory ETA shape mismatch")
        detected = (current >= threshold) | np.asarray([e is not None and 0 <= e <= 300 for e in predicted_eta])
    future = current < threshold
    result = dict(all_windows=confusion(labels, detected), future_onset=confusion(labels[future], detected[future]),
                  currently_over_threshold=int((~future).sum()), method="candidate-specific 0/60/300 trajectory; future onset excludes already-hot windows")
    provided_trajectory = predicted_eta is not None
    if predicted_eta is None:
        predicted_eta = [first_crossing([0, 60, 300], [t, *p], threshold) for t, p in zip(current, predictions)]
    errors = []
    eligible = 0
    if true_eta is not None:
        for t, actual, estimate in zip(current, true_eta, predicted_eta):
            if t < threshold and np.isfinite(actual) and 0 <= actual <= 300:
                eligible += 1
                if estimate is not None: errors.append(float(estimate-actual))
    result["crossing_time"] = dict(mae_s=float(np.abs(errors).mean()) if errors else None,
                                    bias_s=float(np.mean(errors)) if errors else None,
                                    matched_crossings=len(errors), eligible_crossings=eligible,
                                    unavailable_or_missed=eligible-len(errors),
                                    method=("model future-trajectory crossing" if provided_trajectory else "piecewise-linear sparse regression estimate")+"; paired errors do not include missed events")
    return result
