# Software validation record

This is the original 2026-11-14 implementation record. The corrected physics,
independent rail simulator and current tests are documented in
[ENGINEERING_REPORT.md](ENGINEERING_REPORT.md).

Validated locally on 2026-11-14, Python 3.13 CPU, using the supplied original
synthetic fixtures. No commits, pushes, flashing or physical actuation were
performed. Hardware commissioning remains pending.

## Observed commands and results

| Check | Actual result |
|---|---|
| Editable install of `./model[ml,dev]` and `./algorithm[ui,dev]` | Succeeded after approval to access installation/temp directories. |
| `python -m grid_model inspect --scenarios model/data/model_training_scenarios.csv` | 194,400 rows; 36 scenarios; train/val/test 25/5/6; zero spacing gaps. Missing observation rows and unavailable forward labels preserved. |
| Train `persistence`, `rc`, `ridge` and evaluate each on test | Succeeded; local versioned artifacts and JSON metrics generated. |
| Train `lstm` and `transformer` with `--quick`, evaluate each on test | Two CPU epochs completed on two train/two validation scenarios each. Both smoke candidates failed validation selection and safely fall back to RC online. |
| `python -m pytest model/tests algorithm/tests -q` | **44 passed in 70.41s** on the final delivered code. Covers CPU neural training/reload, online parity, malformed/bounded protocol, wide/long adapters, source identity, policy, ACK retry/duplicates, missing sensors, stale/disconnected USB, reset/wrap, protected load, gradual cooling, SQLite/export and Streamlit interactions. |
| `python -m grid_algorithm replay --speed 0 --dry-run` | All 2,993 packets processed; zero generated commands; three recorded transitions (rail 2 off/on, rail 3 off). |
| `python -m grid_algorithm simulate --artifact model/artifacts/ridge-demo --duration-s 1800` | Real mutable feedback loop completed with selected Ridge, two matching APPLIED ACKs, only rails 2/3 shed, zero automatic restores. |
| `python -m grid_algorithm export --log algorithm/runs/demo.sqlite --output algorithm/runs/demo-events.csv` | CSV export succeeded. SQLite WAL logs include raw frames, observations, forecasts, state/decisions, bridge status, commands and applied ACKs. |
| `python -m grid_algorithm live --port IEEE_ADSC_NO_DEVICE --monitor-only --duration-s 2` | Gracefully reported stale telemetry on nonexistent port; no actuation or successful hardware connection claimed. |
| `python -m compileall -q model/src algorithm/src algorithm/dashboard` | Passed. |
| `pio run -d algorithm/firmware/rig_controller` | SUCCESS: dry-run ESP32 A; 24,996 B RAM, 290,141 B flash. |
| `pio run -d algorithm/firmware/bridge` | SUCCESS: dry-run ESP32 B; 25,664 B RAM, 283,561 B flash. |

PlatformIO 6.2.0 used espressif32 6.10.0, Arduino ESP32 2.0.17-based framework,
ArduinoJson 7.4.3, OneWire 2.3.8 and DallasTemperature 4.0.6. Initial toolchain
download required approval. Initial C++ errors were fixed before both successful
builds. OneWire emitted upstream preprocessor warnings; builds succeeded.
The shell used the installed PlatformIO executable when `pio` was not on PATH.

## Held-out temperature errors

730 valid, causal test windows from six test scenarios, 300s lookback, 5s
downsampling and 30s stride. Validation alone selected Ridge regularization and
accepted its candidate; test data were used only for evaluation. Rail ID is
excluded. All errors below are °C.

| Strategy | +60s MAE | +60s RMSE | +300s MAE | +300s RMSE |
|---|---:|---:|---:|---:|
| Persistence | 0.948 | 1.695 | 3.900 | 6.953 |
| RC demo reference | 0.690 | 1.078 | 3.272 | 5.798 |
| Trained Ridge (selected) | 0.352 | 0.680 | 2.742 | 4.822 |
| LSTM (two-epoch smoke only) | 8.686 | 14.499 | 9.617 | 15.746 |
| Transformer (two-epoch smoke only) | 4.496 | 8.752 | 6.273 | 10.852 |

Ridge validation +300s MAE was 2.668°C versus persistence 4.093°C. CPU model
batch-forward times per precomputed test window were approximately 0.005ms for
Ridge, 0.007ms RC, 0.141ms LSTM and 0.292ms Transformer. These exclude online
feature construction and serial/UI latency; they are not a real-time guarantee.

There were 41 positive crossing labels among 730 windows. Endpoint/current
threshold proxy precision/recall was 1.00/0.951 for Ridge and 0.440/0.976 for RC;
these are not calibrated probabilities and may miss intermediate crossings.
RC paired ETA MAE was 5.223s on supported crossing pairs, excluding noncrossings
or missing trajectory estimates. Full per-scenario/type metrics, assumptions and
data fingerprints are in ignored local `model/artifacts/*/` JSON files.

## Closed-loop trace

The learned demo used Ridge without fallback. Eligible branches heated from
35°C to 69.663°C at virtual second 300. Model-based requests passed the
two-observation policy gate, traversed the fake byte-validated bridge and were
applied by the virtual ESP32 A. Both ACKs matched their unique request IDs.
Subsequent samples showed zero current/voltage and delayed cooling to 61.748°C
after 60s. Both rails ended `SHED_CONFIRMED`; protected rail 1 remained `ON`.

The default RC demo also completes with no training files. The passive replay
has pre-scripted interventions and is not used as prediction truth. A fresh
simulation run appends to its SQLite file; select a new `--log` path to keep
individual experiments separate.

## Remaining gates

All physical checklist entries in [README.md](README.md#firmware) remain pending:
board/pin assignments, wiring/ground, sensor calibration, relay polarity and
ratings, fuses/emergency stop/independent thermal cutoff, real limits and supervised
review. Live CLI stays monitor-only and both firmware defaults are simulated.
No real sensors, thermal response, flashing or real relay switching were tested.
Fixture redistribution license remains TBD in [DATA.md](../DATA.md).

CI runs core Python/integration/UI checks, accelerated replay and the RC smoke
without GPU/hardware. Full model tests require the manually supplied local
training CSVs. The workflow was added but no remote Actions run is claimed.
