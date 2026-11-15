# Codex implementation mandate — IEEE × ADSC Extreme Heat Grid Stress Predictor

> **Read this entire file. Implement the project, not just a plan.** This file is written as repository-level instructions for Codex. Create and maintain **two primary software folders in this same repository: `model/` and `algorithm/`**. The project must run end-to-end in simulation without physical ESP32s and must have a clearly gated, documented hardware path for two ESP32 devices. Do not stop after scaffolding or pseudocode.

## 0. Operating rules for Codex

1. First inspect the existing repository and preserve its source, Git history, configuration, and any work teammates already completed. If something here conflicts with working code, reconcile and document the change rather than deleting it.
2. Implement in checkpoints. After each checkpoint run applicable tests, repair failures, and continue autonomously. Prefer functioning, testable code over elaborate abstractions. Avoid asking routine questions; use the defaults in this file and record them. **Stop hardware actuation until the wiring, component ratings, and human-approved safety settings have been confirmed.**
3. Keep the runnable laptop application in `algorithm/`, the forecasting/training code in `model/`, and the firmware for **both** ESP32 devices in `algorithm/firmware/`. The main Python process runs the forecasting model **on the laptop**, not on an ESP32. ESP32 B is a bridge, not an ML inference processor.
4. Do not silently claim to have trained an IEEE-endorsed model, reproduced an IEEE standard, flashed an ESP32, or tested physical sensors. Distinguish verified software tests from unverified hardware integration.
5. Prefer offline-capable, free/open-source tooling; default to Python 3.11+, pandas, NumPy, scikit-learn, PyTorch (optional ML extra), pyserial, Pydantic, pytest, Plotly/Streamlit, and PlatformIO/Arduino for firmware. Avoid required paid cloud services.
6. Do not require external network access at runtime. If dependencies cannot be installed in the Codex environment, still write the implementation and run whatever static, dependency-free, and unit checks are feasible. Report precisely what could not be tested.
7. Ensure the final repository has a root `README.md`, `.gitignore`, `model/README.md`, `algorithm/README.md`, reproducible install/run instructions for Windows PowerShell and Unix shells, and no secrets or machine-specific absolute paths. Make the demo work with a single explicit command after setup.
8. Implement the **MVP/fully closed-loop simulator first**, then ML model alternatives and ESP32 firmware, followed by dashboard/polish. A finished app with a working baseline is more valuable than an untrained fancy neural network.
9. All safety-critical actuator decisions are deterministic and validated on **ESP32 A**; any prediction on the laptop is only a requested intervention. Allow laptop/bridge messages to be lost, delayed, duplicated, or malformed without unsafe toggling.

## 1. What the project actually is

**Project:** IEEE × Aggie Data Science Club (ADSC), *Extreme Heat Grid Stress Predictor*.

**Goal:** Use sensor history (temperatures, DC current, voltage, ambient temperature), a physics-informed thermal reference, and a small forecasting model to predict future hot-spot temperature/time to overheating. Show a countdown/risk status, and automatically disconnect a noncritical **simulated 12 V DC load branch** before it exceeds the chosen demonstration threshold. This is a low-voltage **mock rig**, not an actual mineral-oil power transformer and not a utility-grade protection relay.

**Two software teams / responsibility boundaries:**

- `model/` (Model Team): input validation and preprocessing, physics reference/thermal simulator, synthetic data ingestion, feature extraction, train/validation/test partitioning, persistence/linear baseline, lightweight recurrent/attention models, artifact versioning, model evaluation and uncertainty/failure reporting, online inference interface.
- `algorithm/` (Algorithm + Embedded Team): ingest/replay/normalize sensor packets, rolling windows, call model, monitor stale/missing sensors, decision-state machine, rail priority, relay command generation, retries/ACK handling, local safety, dashboard/logging, simulation plant, laptop USB-serial driver, ESP32 B bridge firmware and ESP32 A controller firmware.

**Expected physical topology:**

```text
  12 V fused bench supply -> three separately switched demo LOAD BRANCHES
                         rail_1   rail_2   rail_3
                         | sensors: voltage/current/temperature + ambient
                  [ESP32 A: esp32_rig_01]
                   sensor sampling + relay outputs + LOCAL interlocks
                             | UART TX/RX + shared 3.3 V logic GND
                  [ESP32 B: esp32_bridge_01]
                   transparent, validated bidirectional message bridge
                             | USB serial (115200 8N1 proposed)
                           [LAPTOP]
     receive -> validate -> forecast -> deterministic policy -> command
                             |
                    dashboard + audit log
```

**Critical electrical distinction:** The term *rail* in the synthetic CSVs means an independently switched **12 V load branch**, **NOT** the ESP32's 3.3 V/5 V logic power rail. Never shed MCU power as a model action. The hardware team must approve supply, fuses, current ratings, MOSFET/relay topology, sensor placements and thermal shutdown independently. USB power to ESP32 B does not imply its regulator can power the 12 V rig or ESP32 A.

**Reference material supplied by the user:** `proj proposal.pdf`, `Meeting_ IEEE × ADSC (1).pdf`, `Extreme Heat Grid Stress Predictor.pdf`, the synthetic CSVs listed below, and a shared conversation link (`https://chatgpt.com/share/6af927c4-46e4-83e9-8c22-390df8aa772a`). The shared URL exposed no readable conversation text to the assistant generating this mandate; **do not invent its contents**. If Codex can actually open it, review for additional requirements, record them, and reconcile them with this spec. The PDFs describe IEEE C57.91 thermal behavior, mock heating element, early overheating prediction, low-priority load shedding, ESP32s, and an eventual model/dashboard; this file specifies the newer, explicit two-ESP32 serial topology chosen in this conversation.

## 2. Nonnegotiable synthetic-data facts (do not change silently)

The user already has a downloadable package `IEEE_ADSC_Heat_Grid_Synthetic_Data.zip`. The optional Codex repository starter ZIP places the usable fixture files into `model/data/` and `algorithm/fixtures/`, and source PDFs into `model/references/`. Read these PDFs if they are present, but this AGENTS.md remains the executable specification.

| Existing fixture | Expected repository location | Purpose |
|---|---|---|
| `model_training_timeseries.csv` | `model/data/` | 194,400 long-format rows = 36 scenarios × 1800 s × 3 rails, 1 Hz, with forward labels |
| `model_training_scenarios.csv` | `model/data/` | Scenario definitions/splits: 25 train, 5 val, 6 test |
| `esp32_telemetry_replay.csv` | `algorithm/fixtures/` | 2,993 wide-format packets from a 50-minute ~1 Hz recorded *synthetic* replay |
| `esp32_control_commands.csv` | `algorithm/fixtures/` | Three illustrative scripted commands, including two automatic shed events and a **manual** restoration |
| `esp32_control_acks.csv` | `algorithm/fixtures/` | Three illustrative matching ACKs |
| `rail_config.csv` | `algorithm/fixtures/` | Three rails, demo warning/critical temperatures, priorities and shed permissions |
| `README_data_contract.md` | `algorithm/fixtures/` | Original synthetic data documentation; preserve as source-of-truth for fixture semantics |

All the rows are **synthetic**, generated by a simplified first-order thermal RC emulator with noise; they are **not ESP32 measurements, an IEEE C57.91 calculation, or utility transformer calibration**. The training trajectories assume **no load-shedding intervention**; the telemetry replay contains scripted interventions. Never pretend that its model predictions came from an actually trained network. Do not mix post-intervention outcomes with no-intervention labels.

### 2.1 Exact model-training CSV columns

```text
scenario_id,data_split,timestamp_utc,elapsed_s,rail_id,
ambient_temp_c,bus_voltage_v,rail_voltage_v,rail_current_a,
rail_power_w,rail_hotspot_temp_c,rail_enabled,sensor_valid,
target_hotspot_temp_plus_60s_c,target_hotspot_temp_plus_300s_c,
target_crosses_80c_next_300s,target_time_to_80c_within_600s
```

- Group/sort by **`(scenario_id, rail_id, elapsed_s)`**, and preserve the scenario's `data_split`. Never let a rolling feature/window cross scenario or rail boundaries.
- Only train against nonnull target values with a complete required look-ahead horizon. At the end of a scenario, blank labels mean *unavailable*, not zero.
- `target_time_to_80c_within_600s = -1` means **no crossing within that bounded 600-second horizon**, not “never overheats”. Blank means the full future horizon was unavailable.
- `sensor_valid=0` means some observations may be blank. Handle missingness, quality flags, short gaps and longer outages explicitly.
- Both current and voltage measurements are DC. A CT clamp alone is generally **not suitable for DC sensing**; the prior fixture assumes a calibrated DC-capable ACS712-class current sensor.
- The 80°C crossing labels and 70°C warning are **illustrative demonstration values, not real-world safety ratings**.

### 2.2 Exact ESP32 telemetry-replay CSV columns

```text
timestamp_utc,uptime_ms,packet_seq,source_device_id,ambient_temp_c,
bus_voltage_v,
rail_1_voltage_v,rail_1_current_a,rail_1_hotspot_temp_c,rail_1_enabled,
rail_2_voltage_v,rail_2_current_a,rail_2_hotspot_temp_c,rail_2_enabled,
rail_3_voltage_v,rail_3_current_a,rail_3_hotspot_temp_c,rail_3_enabled,
total_load_current_a,total_load_power_w,fault_flags,last_applied_command_id
```

- Each CSV **row is one packet** containing all three rails, unlike the *long-format* training file (one row per rail and second). Implement a well-tested conversion to a canonical `TelemetryFrame` with a `rails[]` array.
- Packet sequence numbers intentionally **skip** (dropped samples). Timestamps may have missing temperature readings, `fault_flags` can be pipe-delimited, and disabled-rail downstream voltage appropriately drops to approximately zero.
- Device `uptime_ms` is monotonic from MCU boot; `timestamp_utc` in fixture is generated, not proof of an RTC on an ESP32. In live mode, the **laptop assigns receive time** unless a synchronized device clock exists. Handle uptime rollover/reset/reboot and packet sequence wrap.
- Example fixture command actions: `CMD-0001` auto-sheds `rail_2` near `20:13:42Z`; `CMD-0002` manually restores `rail_2` near `20:26:20Z`; `CMD-0003` auto-sheds `rail_3` near `20:30:36Z`. ACKs match on `command_id`. These are **scripted examples**, not prediction accuracy ground truth.

### 2.3 Demonstration defaults (`rail_config.csv` is authoritative)

| Rail | Role | Nominal bus | Warn / Critical | Auto-shed? |
|---|---|---|---|---|
| `rail_1` | protected, high-priority | 12 V | 70°C / 80°C | **NO** |
| `rail_2` | low-priority heater/load | 12 V | 70°C / 80°C | YES |
| `rail_3` | low-priority lamp/heater | 12 V | 70°C / 80°C | YES |

Default sample interval: 1.0 second. Default forecast horizons: 60 and 300 seconds, with optional ETA to reaching 80°C in the next 600 seconds. Additional rails should be configurable, but 3-rail integration must work first. Treat all temperature thresholds and nominal currents as **modifiable demo parameters**; refuse live physical actuation until the hardware team confirms thresholds and safe switching logic.

## 3. Repository shape — create this, adapting existing files if necessary

```text
repo-root/
├── AGENTS.md                       # THIS FILE — Codex operating instructions
├── README.md                       # complete quickstart and architecture
├── .gitignore
├── model/
│   ├── README.md
│   ├── pyproject.toml               # installable grid-model package, extras [ml,dev]
│   ├── data/
│   │   ├── model_training_timeseries.csv
│   │   └── model_training_scenarios.csv
│   ├── configs/default.yaml
│   ├── src/grid_model/
│   │   ├── __init__.py
│   │   ├── __main__.py              # `python -m grid_model ...`
│   │   ├── contracts.py             # PredictRequest/PredictResponse datatypes
│   │   ├── data.py                  # CSV validation, scenario-aware sequencing
│   │   ├── features.py              # online/offline parity; no leakage
│   │   ├── thermal_rc.py            # calibrated, simple synthetic rig baseline
│   │   ├── physics_ieee.py          # OPTIONAL clearly qualified IEEE reference
│   │   ├── baselines.py             # persistence and sklearn regression
│   │   ├── neural.py                # small LSTM and encoder-only Transformer
│   │   ├── training.py
│   │   ├── evaluation.py
│   │   ├── inference.py
│   │   └── serving.py               # optional local FastAPI interface
│   ├── artifacts/.gitkeep           # artifact metadata+metrics+weights, no huge commits
│   ├── reports/.gitkeep
│   └── tests/
│       ├── test_data_and_windows.py
│       ├── test_training_and_evaluation.py
│       ├── test_online_parity.py
│       └── test_inference.py
└── algorithm/
    ├── README.md
    ├── pyproject.toml               # installable grid-algorithm package, extras [ui,dev]
    ├── configs/demo.yaml            # adjustable policy and serial connection
    ├── fixtures/
    │   ├── esp32_telemetry_replay.csv
    │   ├── esp32_control_commands.csv
    │   ├── esp32_control_acks.csv
    │   ├── rail_config.csv
    │   └── README_data_contract.md
    ├── src/grid_algorithm/
    │   ├── __init__.py
    │   ├── __main__.py              # `python -m grid_algorithm ...`
    │   ├── contracts.py            # canonical wire messages, CSV adapters
    │   ├── protocol.py             # line-delimited JSON encoder/decoder
    │   ├── transport.py            # USB serial + fake in-memory transport
    │   ├── replay.py               # deterministic replay reader
    │   ├── simulator.py            # mutable mock rig plant, independent of ML labels
    │   ├── model_client.py         # local installed model or optional local HTTP
    │   ├── policy.py               # deterministic policy and rail state machine
    │   ├── coordinator.py          # sensor -> forecast -> policy -> command -> ACK
    │   ├── persistence.py          # event log (SQLite) + CSV export
    │   ├── dashboard_state.py
    │   └── cli.py
    ├── dashboard/app.py             # live data, forecast, actions, ACKs
    ├── firmware/
    │   ├── rig_controller/         # ESP32 A — sensors, relays, independent failsafes
    │   │   ├── platformio.ini
    │   │   ├── include/             # hardware_config.h + protocol/safety types
    │   │   └── src/main.cpp
    │   └── bridge/                 # ESP32 B — USB serial <-> 3.3 V UART
    │       ├── platformio.ini
    │       ├── include/
    │       └── src/main.cpp
    ├── runs/.gitkeep                # local logs/sqlite; ignored in Git
    └── tests/
        ├── test_csv_protocol.py
        ├── test_policy.py
        ├── test_transport_and_acks.py
        ├── test_replay.py
        ├── test_closed_loop_simulation.py
        └── test_fault_injection.py
```

Create other small files as needed (e.g., `conftest.py`, C++ headers, CI workflow), but maintain the two primary team directories. The code must be maintainable by students: comments for decisions, straightforward modules, type hints, no unnecessary distributed services.

## 4. Canonical versioned interface — both teams MUST implement the same contract

Use **newline-delimited JSON (NDJSON), one UTF-8 JSON object per line**, on both links (laptop ↔ ESP32 B ↔ ESP32 A) at a configurable 115200 baud, 8N1. Limit line length (e.g., 2048 bytes), validate before routing, define schema version `v:1`, and use `\n` framing. Do not mix firmware debug logs with machine-readable USB serial frames: log diagnostics to a separate sink or as explicit `type:"diagnostic"` messages that the parser can safely ignore. Avoid fragile `readStringUntil` calls that block the control loop indefinitely.

**Telemetry (ESP32 A → bridge → laptop):**

```json
{"v":1,"type":"telemetry","source":"esp32_rig_01","seq":5001,"uptime_ms":0,"ambient_temp_c":26.08,"bus_voltage_v":11.996,"rails":[{"id":"rail_1","v":11.968,"a":0.599,"hotspot_c":35.0,"enabled":true,"sensor_valid":true},{"id":"rail_2","v":11.974,"a":0.540,"hotspot_c":36.9375,"enabled":true,"sensor_valid":true},{"id":"rail_3","v":11.970,"a":0.683,"hotspot_c":37.125,"enabled":true,"sensor_valid":true}],"fault_flags":[],"last_applied_command_id":null}
```

**Command request (laptop → bridge → ESP32 A):**

```json
{"v":1,"type":"command","command_id":"CMD-0001","source":"laptop","destination":"esp32_rig_01","action":"SET_RAIL_ENABLED","rail_id":"rail_2","enabled":false,"reason":"PREDICTED_WARNING_THRESHOLD_300S"}
```

**ACK (ESP32 A → bridge → laptop):**

```json
{"v":1,"type":"ack","command_id":"CMD-0001","source":"esp32_rig_01","rail_id":"rail_2","status":"APPLIED","enabled":false,"controller_uptime_ms":822347}
```

**Recommended statuses:** `APPLIED`, `ALREADY_APPLIED`, `REJECTED_PROTECTED`, `REJECTED_UNARMED`, `REJECTED_UNSAFE`, `REJECTED_INVALID`, `ERROR`; explicitly document any others. A successful ACK should report **actual controller-applied state**, not merely “command received.” If an ACK is lost, resend the **same `command_id`**; ESP32 A must deduplicate and never toggle hardware a second time for a duplicate `SET_RAIL_ENABLED` request. All commands are **set-state**, never “toggle.”

**Schema correctness:** Reject invalid version/type, duplicated rail identifiers, NaNs/Inf, out-of-range data, unsupported command action, overlong frame, stale telemetry, malformed JSON and missing command IDs. Parse booleans consistently (`0/1` in CSV vs true/false in JSON). Sensor failure is represented by null/missing + quality flags, **never by invented 0°C**. Include packet/ack timeout tracking and error counters. Implement serialization round-trip and malformed-frame unit tests. Put one definitive schema/field reference in `algorithm/README.md`; the model's Python inference payload should be compatible with these parsed canonical objects, not coupled to the raw CSV format.

**Model interface:** The model operates per rail, over a causal sequence of sensor observations. Input example (in-memory type or HTTP JSON):

```json
{"rail_id":"rail_2","observations":[{"t_s":0,"ambient_temp_c":26.1,"bus_voltage_v":12.0,"rail_voltage_v":11.97,"rail_current_a":0.54,"rail_hotspot_temp_c":36.9,"rail_enabled":true,"sensor_valid":true}],"forecast_horizon_s":300}
```

Actual live requests contain a configured 300-second rolling history (typically 300 samples at 1 Hz, or 60 samples at a defined 5-second aggregation), not just the example observation. Response MUST include `rail_id`, `observed_hotspot_c`, `predicted_hotspot_plus_60s_c` (nullable), `predicted_hotspot_plus_300s_c` (nullable), `eta_to_80c_s` (nullable), `model_id`, `model_version`, `prediction_time_utc` and `data_quality` (`good`/`degraded`/`invalid`). If an ETA is unknown/outside the supported horizon, use **null**, not “never.” Include optional `threshold_cross_probability_next_300s` only when actually calibrated/evaluated; do not fabricate certainty.

### 4.1 Time synchronization and freshness

Maintain arrival time in the laptop's **monotonic clock** for freshness/watchdogs; use UTC timestamps for dashboards/logs only. The ESP32 can send uptime without accurate UTC. Do not use a sample's synthetic CSV timestamp to decide whether replay telemetry is currently stale. In playback/simulation, use a **virtual clock** so 50 minutes of data can be replayed instantaneously or at any speed with identical decisions. On ESP32 reboot, reestablish session state and require fresh telemetry before commands.

## 5. Model Team implementation (`model/`)

### 5.1 Dataset loader and safety against leakage

1. Validate the exact CSV headers, types, valid rail IDs, monotonic elapsed time per scenario, 1 Hz spacing with any gaps flagged, label-null semantics, sensor flags, and scenario-split integrity. Show a useful CLI `inspect` summary with row counts, missing values, crossing frequency and per-split scenarios.
2. Train only using **past and current measurements**, never using `target_*`, `data_split`, `scenario_id` or a future timestamp as features. For physical generalization, do **not** let the model memorize `rail_id` as a spurious signal; evaluate with/without rail ID and justify if used.
3. Build windows per scenario/rail, with 300-second lookback by default and 5-second downsampling to allow CPU training (adjustable). Use an explicit window stride (e.g., 10–30 s), and ensure online feature construction exactly matches training. Include rolling mean/min/max and temperature-change rate for tabular baseline; temperature, current, voltage, ambient and relay state for sequence models.
4. Fit imputation/statistics/scaling **only on training scenarios**. Use a missingness mask and sensor quality flags. Skip long faulty windows; allow short gaps with forward fill up to a documented limit, not leakage from the future.
5. Preserve each source split: train **25**, val **5**, test **6** scenarios. No random row split, even for quick training. Support `--seed` for deterministic behavior.

### 5.2 Three working forecast strategies, implemented in priority order

**A. Always-working baseline (mandatory):** persistence (`T_future = T_now`) and a small regression forecaster (Ridge or tree regressor) on causal window features, trained with scikit-learn. Save preprocessing pipeline + model + metadata. This must run on a normal laptop without a GPU.

**B. Physics-guided baseline (mandatory):** configurable first-order RC branch model, e.g. `dT/dt = (T_ambient + R_thermal * electrical_power - T) / tau`. Numerically integrate with the actual time interval. Initialize sensible demo-only defaults and optionally fit `R_thermal, tau` from training-scenario histories. Never assume those parameters represent a real transformer. Provide a basic unit test (constant power tends to stable temperature, disabled power cools, no instantaneous impossible temperature step). Forecast assumes an explicit **no-intervention** loading scenario and states that assumption.

**C. Neural comparison (mandatory, but cannot block MVP):** implement a compact PyTorch LSTM and a 2-layer encoder-only time-series Transformer (e.g. hidden size 64, four heads, dropout, sequence length 60 after 5-second downsampling). Both predict future temperature at **+60s and +300s** from causal inputs. Expose `train --model lstm|transformer`; run small CPU smoke training with 1–2 scenarios/very few epochs, and offer full-dataset training. Models are random-initialized and must be trained; no fictional pretrained weights. Enforce deterministic seeds, validation early stopping, batching, model checkpoint metadata, and inference CPU compatibility. Keep optional PyTorch dependencies isolated in extras so the baseline app still installs quickly.

**D. IEEE/IEC thermal standards as an explicitly qualified reference (prefer after A/B/C):** The attached project concept calls for **IEEE C57.91** hot-spot/top-oil/aging equations, but the provided CSVs are for a 12 V thermal emulator, not an oil-immersed transformer. Provide a separate `physics_ieee.py` adapter or documented mathematical reference for hot-spot, top-oil lag and insulation-age acceleration **only if equations, assumptions, ratings and references can be verified**. Do not label an arbitrary RC simulator as IEEE-compliant. An alternative comparison, **Alliander's open-source `transformer-thermal-model`**, implements **IEC 60076-7**, **not IEEE C57.91**; it requires transformer specifications and can be offered as an optional offline experiment rather than forced into the 12 V mock rig. URL: `https://github.com/alliander-opensource/transformer-thermal-model` (MPL-2.0). Do not copy proprietary standard text. Clearly label which reference produced which output, and never assert the oil-immersed equations are hardware-calibrated without real transformer inputs.

### 5.3 Evaluation, artifacts, online forecasts

- For each strategy, report **MAE/RMSE at 60s and 300s**, per scenario type and test split, plus inference latency on CPU. Compute threshold-crossing precision/recall for the **80°C within 300s** target when model outputs can support it, and absolute ETA error on crossing episodes when available. Report calibration limitations and class imbalance; include a trivial persistence score. Never manufacture measured accuracy.
- Use the validation split for choice/tuning; evaluate test only after selection; prevent training on test. Save `artifacts/<run-id>/` containing model weights, normalization, hyperparameters, feature schema, threshold assumptions, training-data fingerprint, metrics, git commit if available and clear label `synthetic_only`.
- Make `python -m grid_model inspect`, `train`, `evaluate`, and `predict` commands with `--help`, direct paths, and clean errors. Support `--model persistence|ridge|rc|lstm|transformer`.
- The inference call must return both forecast temperatures and an ETA only when supported by a valid future trajectory. Do not estimate ETA using a single +300s point and present it as exact; if a rough interpolation is shown, explicitly mark it as an estimate and cap it to horizon. Quality should be `degraded`/`invalid` with null forecasts if input is insufficient, stale or largely missing.
- If training/performance goes poorly, **automatically fall back** to the last validated baseline instead of crashing the demo. The README should explain this decision. For closed-loop safety, prediction alone is never trusted above the local safety limits.

## 6. Algorithm Team laptop implementation (`algorithm/`)

### 6.1 Ingestion modes — all three must exist

**Mode 1: deterministic passive CSV replay:** Read `esp32_telemetry_replay.csv` and parse its wide-format columns into typed `TelemetryFrame`s; optionally compare replayed scripted command/ACK records from fixture CSVs. The replay contains *pre-scripted* relay changes. In passive replay mode **never send live commands, and never let newly generated commands modify the recorded sequence**. Optional `--speed 1|10|50|0` (0 means as fast as possible), `--limit`, `--start-offset`, and a virtual clock.

**Mode 2: truly closed-loop software simulation (primary acceptance test):** Implement a mutable 3-rail mock thermal plant with independent current/temperature states and configurable load profiles (normal, ramp, abrupt overload, hot ambient, dual overload), bus voltage droop, sensor quantization, occasional noise/faults, and **real state changes when simulator receives command requests**. A simulator ACK comes from an emulated ESP32 A and its next samples must show rail voltage/current near zero followed by delayed cooling; **do not falsely show cooling immediately**. Use configured thresholds and safe electric/thermal bounds. Seeded virtual time means deterministic runs, no physical devices. This mode tests the complete loop: sensor → model → policy → command → bridge → rig actuator → ACK → cooled sensor feedback.

**Mode 3: physical USB serial:** Connect the laptop to **ESP32 B** via a user-selected port (e.g., `COMx` on Windows, `/dev/ttyUSBx` on Linux), never hardcode a previous project's COM4. ESP32 B bridges the verified messages to ESP32 A over wired 3.3 V UART (unless the hardware team later explicitly chooses ESP-NOW). Do not silently switch to Wi-Fi or MQTT; they are optional future adapters. Use reconnect/backoff, framing/CRC or robust parse checks, ACK timeout, and a bounded command queue. The default physical mode is **monitor only / no actuation**; require explicit operator arming, correctly configured GPIO and physically verified safety interlocks before any relay actuation.

### 6.2 Decision policy (deterministic, testable, independent of ML)

- All decisions use `rail_config.csv`, not magic literals. **Never automatically shed `rail_1`**. Only `rail_2`, `rail_3` permit automatic disconnect, and disabled rails are never silently restored.
- Default demo warning is 70°C, critical 80°C. Request a shed when valid **predicted +300s hot-spot** exceeds/equal configured warning threshold **and confidence/data-quality gating passes**, or when measured temperature reaches a confirmed warning/critical condition. Hysteresis, minimum prediction persistence (e.g. 2 consecutive valid frames), and a short cooldown protect against relay chatter. Make these configurable. Predictive triggers should carry the actual model, horizon and reason in the audit log.
- For an already-off rail, **do not issue repeated shed commands** each sample. For high-priority `rail_1`, raise a visible alarm instead of overriding its `shed_allowed=0` rule. An independent, approved emergency hardware cutoff may override normal priority, but that is an electrical safety pathway outside regular app policy.
- Manual restoration must be an explicit authorized operator operation and only when the rig controller reports safe-to-restore conditions; never use the model's lower forecast alone to automatically reenable. Include a minimum-off-time, optional restored-load recheck, and logged operator identity/source for manual actions.
- Define state machine per rail: `ON`, `SHED_REQUESTED`, `SHED_CONFIRMED`, `RESTORE_REQUESTED`, `FAULT/UNKNOWN`. A matching `APPLIED`/`ALREADY_APPLIED` ACK plus observed relay state completes transitions. Reject/out-of-order ACKs cannot change the wrong rail.
- Use stable, unique `command_id`; resend **identical command id** on timeout, with bounded retries and backoff (e.g. 1000 ms default and 3 max attempts); ignore late ACKs safely while retaining audit trail. In physically unsafe/faulted conditions, stop new operations, alert operator and rely on controller-local cutoff; never assume the host is always connected.
- Malformed, stale or missing sensor data: mark the rail invalid/degraded and **do not base a new predictive actuation solely on an untrustworthy value**. Independent controller thermal cutoffs remain active, and dashboard must display sensor fault. Explicitly test lost serial, MCU resets, missing temperature, current out of range, duplicate packets, and contradictory relay reports.

### 6.3 Logging and dashboard

- Use SQLite WAL for events so live ingestion and dashboard readers can coexist. Log raw inbound frame, normalized per-rail observations, model forecast + model version, policy decision/reason, outgoing command, bridge status, applied ACK, timing, errors, and current rail state; add CSV export. Store no hard-coded credentials.
- Provide a usable Streamlit or equivalent local dashboard showing: three rails, live current/voltage/ambient/hot-spot temperatures, observed vs predicted temperatures (+60/+300 seconds), warning/critical indicators, time-to-threshold **only if forecast is valid**, relay on/off, command/ACK log, data freshness/fault banner, automatic shed events and explicitly gated manual restore. When using replay, label all information **SYNTHETIC / DEMO ONLY**. Never show a made-up model confidence percentage.
- Provide CLI log output that's informative enough to understand decisions without the dashboard. Do not make the dashboard a dependency of the core algorithm. A failed UI must not disable local safety logic.

## 7. ESP32 firmware — both images must compile; physical output remains gated

Use `PlatformIO` with default dev board id `esp32dev` and Arduino framework; make board configurable without code changes. Only assume generic **ESP32 DevKit** until the hardware team confirms exact boards. The firmware must build even when actual sensor/relay pin mappings are not yet supplied, via a clearly labeled `SIMULATED_IO`/`DRY_RUN` build configuration. Build is not proof of successful flashing or safe hardware operation.

### ESP32 A: `algorithm/firmware/rig_controller/`

Responsibilities:

1. Sample ambient and per-branch thermal/current/voltage observations near 1 Hz. Implement configurable sensor adapters for **DS18B20**-class 1-Wire temperature and **ACS712 DC-capable** current sensor, with calibration constants/placeholders; never guess the ADC calibration/pin mapping or claim unsupported sensors are physically present. Mock sensor backend must be fully functional for development. Avoid blocking the watchdog during DS18B20 conversion (12-bit conversions can take substantial fractions of a second).
2. Send versioned telemetry with `seq`, `uptime_ms`, per-rail state, faults. Use an appropriately sized fixed buffer/ArduinoJson or a bounded serializer; enforce the line-length limit.
3. Receive `SET_RAIL_ENABLED` set-state commands through the inter-ESP UART; validate schema, destination, rail ID, shed permission, arming state, current fault state and manual-restore interlock **locally**. Apply idempotently and reply with precise status and applied state. Keep bounded recent IDs for duplicate ACK behavior.
4. Independent local fault protection: overtemperature/overcurrent/dangerously invalid sensor behavior must trigger configured safe shutdown of the **affected eligible load(s)** and/or heater power, without requiring the laptop. Protected loads have a separately defined emergency safety behavior approved by hardware lead; **regular software must not silently override the protected-load policy**. Physical fuses, thermal cutoff and emergency stop are hardware responsibilities, not something firmware alone can guarantee.
5. Never initialize undefined relay GPIOs in an energized state; relay **active-high vs active-low** must be an explicit hardware setting. In `SIMULATED_IO` firmware no physical GPIO can energize any heater/relay. Physical output path must require a compile-time enable **and** explicit runtime arming.
6. Keep all device behavior nonblocking, with watchdog/heartbeat and a link-failure policy agreed with the hardware team. Use an unambiguous safe initial state for the physical rig; do not auto-reenergize a load after reboot.

### ESP32 B: `algorithm/firmware/bridge/`

Responsibilities:

1. Connect to laptop USB serial and ESP32 A via an assigned hardware UART. Forward valid telemetry/ACKs upstream and valid command requests downstream, preserving `command_id`, `seq`, rail ID and message body. Optionally attach link metadata in separate status frames; do not modify controller readings.
2. Parse NDJSON without indefinite blocking; limit size, count CRC/JSON failures, avoid forwarding malformed commands, and provide bridge status/heartbeat. Do **not** run ML inference, overwrite requested rail states, or claim to actuate relays.
3. Allow `SIMULATED_IO` bridge compilation and protocol tests before pins/hardware are confirmed.

### Hardware integration checklist that MUST remain marked pending until verified

- [ ] Exact ESP32 A/B board variant, UART TX/RX pins on each device, cross-connect TX→RX and **common GND**; **3.3 V logic only**, no 12 V on GPIO.
- [ ] Exact sensor count and location (temperature, bus voltage, per-rail current), DS18B20 pin and pull-up, current-sensor type and ADC scaling, calibration, supply grounding/noise treatment.
- [ ] Relay/MOSFET module rating, safe load current, active-high/active-low state, default-off polarity, fuses, independent thermal cutoff, emergency-stop path, load branch priority.
- [ ] Confirm real temperature thresholds (70°C/80°C in fixture are **not approved operating limits**), ambient conditions, maximum heater surface temperature and safe emergency action.
- [ ] Test serial-only behavior with all outputs physically disconnected, then LED/dummy output, then supervised low-power load, then full demo with faculty/hardware-team safety review.

## 8. Integration and traceability tests — do not skip

**Run on a clean checkout after normal dependency installation.** Create reproducible fixtures and smoke tests that finish quickly, plus an optional longer training benchmark.

1. **Fixture compatibility:** each provided CSV parses; row/sample counts match known source; 36 scenario IDs; splits are 25/5/6; no sample window crosses scenario/rail; null/`-1` target semantics preserved. Export/import wide ↔ canonical long without mixing timestamps.
2. **Forecast correctness:** persistence baseline predicts exactly last valid observed temperature; RC heating/cooling follows physics qualitatively; regression train/inference have identical preprocessing; model artifacts reload; LSTM/Transformer forward pass and a very short CPU training run complete; output contains both 60/300-second predictions or honest null quality indicator.
3. **Protocol:** sample telemetry/command/ACK round-trip; malformed JSON/overlength/NaN/unknown version rejected; no command id collision; out-of-order sequence, missing packet and device reboot handled; false/0 CSV parsing is correct.
4. **Policy:** `rail_1` never auto-shed; `rail_2` and `rail_3` can shed; no oscillating relay commands; no automatic restore; insufficient data does not create an arbitrary command; missing/stale telemetry creates a visible fault; duplicate ACK/command is idempotent.
5. **Two-device path:** run laptop ↔ fake ESP32 B ↔ fake ESP32 A using the **same protocol classes** as USB serial mode. Confirm retry/ACK, matching IDs and audit trail, and that forwarding does not invent a physical relay state.
6. **Passive replay:** replay all ~2,993 rows at `--speed 0` without hardware and finish; demonstrate expected recorded transitions from the *fixture* without treating them as new algorithm-generated actions.
7. **Closed-loop proof:** in a deterministic escalating-rail scenario, observe actual thermal ramp, model forecast, `rail_2`/`rail_3` shed request, ACK, switch-off in virtual plant, measured current/voltage dropping, and gradual cooling. Print a machine-readable event summary. Assert no `rail_1` auto-shed and zero automatic restores.
8. **Fault injection:** inject bad sensor readings, stale data, duplicate commands, USB disconnect, missing ACK, rig reboot and dashboard crash; tests pass and no unsafe reenergization occurs.
9. **Firmware:** run `pio run -d algorithm/firmware/rig_controller` and `pio run -d algorithm/firmware/bridge` (only if PlatformIO/toolchain available). Report builds separately; do not imply successful flashing.
10. **CI:** add a lightweight GitHub Actions workflow for Python lint/types or syntax, tests and baseline smoke, if repository policy allows. Do not require GPU, physical ESP32s or 50 minutes of wall-clock time.

## 9. Required CLI and reproducible operator workflow

Codex must implement commands equivalent to these (adapt CLI spelling only if the README and tests reflect it accurately):

```bash
# From repository root. Use quotes around local editable paths on Windows.
python -m pip install -e './model[ml,dev]'
python -m pip install -e './algorithm[ui,dev]'

# Validate fixtures and immediately get a model baseline.
python -m grid_model inspect --data model/data/model_training_timeseries.csv --scenarios model/data/model_training_scenarios.csv
python -m grid_model train --model ridge --data model/data/model_training_timeseries.csv --output model/artifacts/ridge-demo
python -m grid_model evaluate --artifact model/artifacts/ridge-demo --split test

# Fast, fully offline data replay: no actuation and no physical ESP32 required.
python -m grid_algorithm replay --data algorithm/fixtures/esp32_telemetry_replay.csv --speed 0 --dry-run

# Full end-to-end virtual rig, using learned baseline, protocol, commands and ACKs.
python -m grid_algorithm simulate --scenario dual_overload --duration-s 1800 --speed 0 --artifact model/artifacts/ridge-demo

# Core unit + integration tests.
python -m pytest model/tests algorithm/tests -q

# Optional small neural training/evaluation (must run on CPU; full version is separate).
python -m grid_model train --model lstm --data model/data/model_training_timeseries.csv --quick
python -m grid_model train --model transformer --data model/data/model_training_timeseries.csv --quick

# Hardware builds (only when PlatformIO is installed; these are not flash commands).
pio run -d algorithm/firmware/rig_controller
pio run -d algorithm/firmware/bridge

# Actual live USB serial mode remains monitor-only without safety commissioning:
python -m grid_algorithm live --port YOUR_ESP32_B_PORT --baud 115200 --monitor-only
```

Support `--help` for every subcommand. If no sample data exists on disk, do not silently proceed with made-up results: print explicit paths expected and explain that the user should copy in the existing fixture CSVs or unpack the supplied starter zip. Code can optionally generate *clearly labeled new synthetic* fixtures with a fixed seed, but must not replace the original test references silently.

## 10. Implementation order / deliverables Codex must finish

**Checkpoint 1 — repo and interface:** inspect project, put files in expected directories, create packaging/README, typed schema, CSV loaders/adapters and tests. Commit/present file tree and test output (never claim commit if not created).

**Checkpoint 2 — working deterministic demo:** implement synthetic plant, UART-style virtual bridge/controller, controller policy, rail state machine, ACK/retry and CLI. Demonstrate actual cooling following load shed in logs. At this checkpoint the app already works with persistence/RC fallback and no trained neural model.

**Checkpoint 3 — complete model team:** train/evaluate persistence, ridge, RC; implement LSTM and mini Transformer training and inferencing; compare on held-out scenarios, save artifacts, expose a stable predictor interface. The model must make **its own** predictions, not replay or copy labels.

**Checkpoint 4 — live transport/firmware:** build ESP32 A + B PlatformIO firmware; verify NDJSON routing and simulated sensor/actuator paths; add USB serial reader, reconnection, safe monitor-only mode and explicit live actuation gating. Hardware-flashing/physical operation remain pending until pins and safety are provided.

**Checkpoint 5 — dashboard/QA:** implement local dashboard, audit log, fault injection, smoke scripts, end-to-end integration test and finalized READMEs. Validate every requirement in Section 8; fix bugs rather than describing them as TODOs. Provide a brief final report listing commands actually run, outcomes, selected baseline, unverified hardware items, and any genuinely unresolved risks.

## 11. Explicit boundaries and decisions for unresolved hardware inputs

- **Decided now:** laptop hosts model; ESP32 B is USB serial bridge; ESP32 A measures/acts; separate 12 V branches; default 3 rails; Python model/algorithm; 1 Hz NDJSON; default 115200 baud; two team directories; mocked first; synthetic CSV schemas; local-only dashboard; no automatic restoration.
- **Still needs the hardware team:** exact boards and MCU pinouts, relay polarity, current/voltage sensor models and calibration, number of thermal sensors and mapping, heater ratings, whether the ESP32s share ground and how isolated power is provided, approved warning/critical thresholds, power budget, wiring and emergency-stop design, real sensor captures. Keep all hardware-dependent code **configurable and dry-run by default**.
- **Accuracy/science boundary:** IEEE C57.91 applies to transformer thermal/aging calculations under its specified assumptions; the demonstration's resistor/heater + DS18B20 sensor readings are **not necessarily winding hot-spot temperatures**. Treat the measured probe as a **hot-spot proxy** and validate/fit any mapping. Any model trained solely on the supplied RC-generated values must be labeled **synthetic proof-of-concept**, not validated transformer overload prediction. Use separate datasets/parameters for actual IEEE/IEC comparison.
- **Security/operations boundary:** do not expose remote relay-control endpoints to the public Internet. Manual restoration is an explicit supervised local operator action, not an unauthenticated HTTP request. Any live relay behavior needs an independently functioning hardware safety cutoff.

## 12. Definition of DONE

The project is **not done** when only modules or notebooks exist. It is done (software perspective) when a teammate can clone the repo, install dependencies, run baseline training, replay synthetic ESP32 telemetry, execute a **real closed-loop software simulation** that sheds only eligible branch loads, observe ACKs and cooling, inspect a dashboard/CSV/SQLite event history, run tests successfully, and build both dry-run ESP32 firmware projects. Live physical switching is an explicit later commissioning step, **not a prerequisite for calling the software complete**.

At the end, Codex must output: a concise repository tree, exact installation/run commands, test and firmware build results **actually observed**, a short description of the forecast model that really ran, and the hardware commissioning checklist that remains unresolved. If one stage cannot run due to environment limitations, explain why, preserve working lower-priority stages, and state the exact outstanding command rather than claiming success.
