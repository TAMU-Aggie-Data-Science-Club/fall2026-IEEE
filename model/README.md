# Model team: synthetic thermal forecasting

Install from repository root: `python -m pip install -e './model[ml,dev]'`.
Python 3.11+ is required. PyTorch is isolated in the optional `ml` extra;
persistence, Ridge and RC run without it. Inference is on the laptop CPU.

## Data and commands

Copy the supplied `model_training_timeseries.csv` and `model_training_scenarios.csv`
into Git-ignored `model/data/`. Missing inputs produce explicit errors. Original
fixtures are never regenerated/replaced. See [DATA.md](../DATA.md).

```sh
python -m grid_model inspect
python -m grid_model train --model ridge --output model/artifacts/ridge-demo
python -m grid_model evaluate --artifact model/artifacts/ridge-demo --split test
python -m grid_model train --model persistence --output model/artifacts/persistence-demo
python -m grid_model train --model rc --output model/artifacts/rc-demo
python -m grid_model train --model lstm --quick --output model/artifacts/lstm-smoke
python -m grid_model train --model transformer --quick --output model/artifacts/transformer-smoke
python -m grid_model predict --input request.json --artifact model/artifacts/ridge-demo
```

These commands work in PowerShell and Unix. Omit `--quick` for full neural
training; `--epochs 20` and `--seed 42` are supported. Quick training uses the
first two training and two validation scenarios for two CPU epochs: an execution
check, not evidence of model superiority. Both neural encoders have 64 hidden
units. The Transformer has two layers, four heads and positional encoding.
Training uses deterministic seeds, mini-batches and validation early stopping.
No pretrained weights are supplied.

`--config model/configs/default.yaml` accepts JSON-compatible YAML. Defaults:
300s lookback, 5s downsampling, 30s stride, 5s short forward-fill limit. No
backward fill occurs. Long gaps invalidate windows; sequence inputs include
missingness and quality channels. Short online gaps yield degraded forecasts
that cannot drive predictive shedding; insufficient/long-faulty windows yield nulls.

Windows stay within `(scenario_id, rail_id)`, preserving 25/5/6 scenario splits.
Full lookahead is required. Blank labels stay unavailable; ETA `-1` means no
crossing in 600s, never infinite lifetime. Only training data fit normalization.
Validation selects Ridge alpha and neural early stopping; test never fits/tunes.
Rail ID, scenario ID, timestamps, split and targets are excluded from features.
Tabular features include causal sensor statistics, rate, quality, power and RC
reference forecasts; `features.py` is shared for batch/online parity.

## Inference, evaluation and selection

`Predictor.predict(PredictRequest(...))` accepts canonical per-rail histories.
Responses include observed temperature, nullable +60/+300s temperatures, model
identity/version, UTC prediction time, quality and bounded trajectory ETA.
Persistence returns the last valid current sample exactly. RC analytically
integrates `dT/dt=(ambient+3.2*power-T)/300` under constant forcing. Only RC
reports ETA, capped at 600s. Two neural/regression endpoints do not establish
an exact crossing trajectory. Predictions assume **no future intervention**.

Artifacts store weights/pipeline, normalization, feature schema, hyperparameters,
seed, data SHA-256, Git revision, synthetic label, validation metrics and demo
thresholds. Evaluate writes `metrics-<split>.json`: MAE/RMSE at each horizon,
per-scenario/type results, CPU latency, persistence comparison, crossing
precision/recall and paired RC ETA error where supported. Endpoint-based crossing
classification can miss intermediate crossings. No calibrated confidence is
claimed; missing ETA is null, not never.

Candidates worse than persistence at +300s on validation remain available for
evaluation but online inference selects the tested deterministic RC fallback.
Missing/unloadable artifacts also select RC with a recorded reason. Quick
neural weights may be rejected. Load only trusted local joblib artifacts.

## Scientific limits

This is a **synthetic proof of concept**, not IEEE-endorsed or calibrated to a
transformer. The attached PDFs describe C57.91 ambitions and older MQTT/CT-clamp
proposals; [ENTROPY_AGENTS.md](../ENTROPY_AGENTS.md) supersedes those with the DC
emulator and wired two-ESP32 topology. CT clamps alone do not measure DC.
IEEE C57.91 equations are deliberately not implemented without verified standard
assumptions and transformer ratings. Alliander's optional transformer thermal
model is an IEC 60076-7 comparison, not IEEE C57.91; it is not a dependency or
claimed result here. The shared URL exposed no readable conversation text.
