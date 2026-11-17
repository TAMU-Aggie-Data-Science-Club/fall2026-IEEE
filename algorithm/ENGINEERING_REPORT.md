# IEEE × ADSC engineering report — 2026-11-15

The architecture correction is implemented and software-tested. IEEE conventional
oil-transformer physics and actual Alliander IEC physics are separate from the
12 V RC emulator. Original Ridge weights, metadata and historical metrics remain
unchanged. No commits/pushes, flashing or physical relay operation were performed.

## What works

- IEEE C57.91-2011 conventional Clause 7 oil/winding dynamics, corrected oil time
  constant, top-oil/hot-spot forecasts at 60/300s and Clause 5 thermal aging.
  Parameters/units are explicit; arbitrary insulation life is not assumed.
- Installed, unmodified Alliander **0.5.0**, using its real documented schema,
  initial-load state and `Model.run()` API. It implements **IEC 60076-7**, not IEEE.
  Reference tests agree with independently calculated analytical cases.
- Dashboard selection of IEEE, IEC, fitted RC or original Ridge, with producing
  model, assumptions, forecast temperatures and warnings. Oil-model actuation is
  blocked by both model/coordinator and policy domain checks.
- Independent three-rail thermal/load profiles, bridge/controller/ACK loop,
  protected rail, local interlocks and explicit supervised restoration retained.
- **66 tests passed in 113.92s**, including old model/algorithm tests, neural CPU
  smoke training, IEEE/IEC references, metrics, failed ACKs, serial framing,
  domain safety and full-1,800-sample dashboard updates. No fragment-rerun warning
  was reproduced in the full-run UI test. Syntax checks passed.
- IEEE and Alliander dashboard analysis modes also passed direct UI smoke checks;
  direct CLI forecasts returned both horizons/top-oil temperatures and explicitly
  separated estimated state from absent measurements.

## Why 39.4% validation recall and identical metrics occurred

The original metadata records Ridge **and persistence** validation precision 1.0
and recall **13/33 = 39.4%** over 609 windows. The evaluator did call each model's
own predictions; it did not reuse the persistence array. However,
`max(current_temperature, prediction_at_300s) >= 80` counted already-hot samples
as successful detections. Both models could detect those 13 while missing advance
crossings. Identical scores therefore hid poor early warning. Good temperature
MAE did not establish good event detection. This validation split must not be
confused with the six-scenario test split.

The corrected evaluator records per-model prediction fingerprints, uses each
model's own 0/60/300 trajectory and reports **future onset separately**, excluding
already-hot samples. Confusion counts and crossing-time coverage are explicit.
Tests deliberately give models different predictions and assert different scores.

## Original RC-fixture test results

730 test windows, including 32 already-hot windows and **9 future-onset positives
among 698 currently-cool windows**. Events mean crossing 80°C within 300s.

| Strategy | MAE 60/300s, °C | Future precision | Future recall | FN | FP | Crossing-time MAE |
|---|---|---:|---:|---:|---:|---|
| Persistence | 0.948 / 3.900 | undefined (no alarms) | 0% | 9 | 0 | unavailable |
| Original Ridge, fixed 80°C | 0.352 / 2.742 | 63.6% | 77.8% | 2 | 4 | 50.6s, 7/9 matched |
| Nominal RC | 0.690 / 3.272 | 13.6% | 88.9% | 1 | 51 | 19.6s, 8/9 matched |
| Training-fitted RC | 0.470 / 2.685 | 17.4% | 44.4% | 5 | 19 | 67.3s, 4/9 matched |
| Ridge advisory operating point | unchanged Ridge | 38.1% | **88.9%** | **1** | 13 | original temperature trajectory only; additional warnings may have no ETA |
| HistGradientBoosting event classifier | event-only | 6.2% | 88.9% | 1 | 121 | no trajectory/ETA |

The Ridge warning operating point, **77.3446°C forecast score for an 80°C event**,
was chosen on validation to reach at least 90% recall with minimal false positives
(validation 18/20 detected, 8 false alarms). It was selected over the classifier
on validation, not test. It is an advisory setting, not a changed physical safety
limit or a calibrated probability. Ridge temperatures/weights are unchanged.
The classifier's false-alarm burden was unacceptable for recommendation.
Fitting RC improved temperature MAE but **worsened detection recall**; this is
reported rather than selecting models solely by MAE. No fitted model is declared
physically calibrated. Nine test onsets are insufficient for broad accuracy claims.

Crossing-time errors use only matched events and disclose missed/unavailable
counts. Regression times interpolate sparse points and are estimates; physics
times use computed future trajectories. Scores contain no fabricated confidence.

## Separate compatible transformer experiments

18 synthetic transformer scenarios, 10/4/4 train/validation/test. References were
generated separately by IEEE and IEC, not from the RC rig and not measured truth.
184 test windows per reference; forecasts hold the latest load while future
reference load can change. A **separate transformer Ridge surrogate** is trained
only on generated training scenarios; the original RC Ridge is out of domain.

| Reference | Forecast | MAE 60/300s, °C | Future precision/recall | FN | Crossing-time MAE |
|---|---|---|---|---:|---|
| IEEE-generated | IEEE | 0.090 / 1.781 | 100% / 100% | 0 | 0s, 10/10 |
| IEEE-generated | Alliander IEC | 1.208 / 2.977 | 100% / 80% | 2 | 52.4s, 8/10 |
| IEEE-generated | transformer Ridge | 0.270 / 3.033 | 87.5% / 70% | 3 | 32.8s, 7/10 |
| IEC-generated | IEEE | 1.219 / 3.007 | 83.3% / 100% | 0 | 52.1s, 10/10 |
| IEC-generated | Alliander IEC | 0.089 / 1.752 | 100% / 100% | 0 | 0s, 10/10 |
| IEC-generated | transformer Ridge | 0.260 / 2.921 | 85.7% / 60% | 4 | 10.7s, 6/10 |

These are model-consistency/disagreement results, **not evidence of physical
accuracy or superiority of a standard**. Same-model perfect crossing timing is
expected in this constructed experiment. Full RMSE, confusion counts, parameters
and CPU measurements are in ignored `model/reports/physics-comparison/comparison.json`.
All run on CPU, no GPU: IEEE is a small linear-time history calculation; Alliander
adds pandas/NumPy/Pydantic and library model construction. Observed history-replay
forecasts take sub-ms to several ms; Ridge forward prediction is several µs per
window with precomputed features. These timings have different included work and
are not latency guarantees. Peak RAM was not measured.

## Independent rails, communication and hardware limits

The old rails 2/3 were mathematically identical: same initial state, loading,
thermal resistance and time constant. They now have distinct values, overload
onsets, load ripple and cooling lags, while retaining shared bus droop. In the
1,800-sample original-Ridge run, rail 2 shed at **292s / 70.09°C** and rail 3 at
**300s / 63.68°C**. After 60s they cooled to **62.56°C / 57.89°C** with zero
current. Both ACKs matched; zero protected-rail sheds and zero automatic restores.
The fitted-RC run also completed with distinct trajectories and matching ACKs.

An emulated USB serial device drives the actual `SerialTransport` through partial
NDJSON reads and controller-generated ACKs, using the same frame bytes as the
fake ESP32 B/A path. Monitor-only defaults, protected rails, sensor faults,
timeouts, duplicate commands, wrong source/rail IDs and rejected ACKs are tested.
Full passive replay still processes 2,993 packets with no generated commands.
Nonexistent-port monitoring reports stale data safely. Firmware wire format is
unchanged; earlier successful dry-run builds remain a historical build result,
not a new physical test. No real ESP32 USB/UART, sensor or relay was verified.

Still required: actual transformer heat-run/rating data and manufacturer review;
physical RC calibration; board/pins/ground/sensors/ADC calibration; relay polarity,
ratings, fuses, independent thermal cutoff/emergency stop, approved real limits
and supervised commissioning. Physical serial mode remains monitor-only and
physical relay outputs remain disabled. See [PHYSICS.md](../model/PHYSICS.md) for
source equations, edition, assumptions and reference cases.

## Reproduce

From repository root, PowerShell or Unix, after supplying original local fixtures:

```sh
python -m pip install -e './model[physics,ml,dev]' -e './algorithm[ui,dev]'
python -m grid_model compare-physics
python -m grid_model calibrate-rc
python -m grid_model compare-detection
python -m grid_algorithm simulate --artifact model/artifacts/ridge-demo --duration-s 1800
python -m streamlit run algorithm/dashboard/app.py --server.address 127.0.0.1
python -m pytest model/tests algorithm/tests -q
```

Ridge weights SHA-256: `e4d30959afb3826e67305daa15f2048494593d962873cf7eb832696e0f151e53`.
A separate full retraining reproduced its coefficients/intercepts with maximum
absolute difference **0.0**. New comparisons do not overwrite original artifacts.
Local code changes are uncommitted on `darsh`.
