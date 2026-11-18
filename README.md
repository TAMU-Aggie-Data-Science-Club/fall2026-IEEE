# IEEE × ADSC Extreme Heat Grid Stress Predictor

A laptop forecasts hot-spot proxy temperatures and requests low-priority **12 V demo branch** shedding through ESP32 B (bridge) and ESP32 A (local interlocks). The full loop runs without hardware. All supplied fixtures and virtual results are **synthetic proof of concept**, not IEEE-endorsed or hardware-calibrated protection.

The selected two-board link is now **USB serial + ESP-NOW unicast**:

```text
Laptop models/policy/dashboard/logs ↔ USB 115200 ↔ ESP32 B bridge
                                           ↕ ESP-NOW (no router)
                              independently powered ESP32 A controller
                                           ↕ local interlocks
                             12 V branches: rail_1 protected, rail_2/3 eligible
```

Actual wireless communication can use simulated sensors with **zero physical
relay outputs**. Local peer MACs/channel/optional encryption keys must be
provisioned; default builds print their own actual MAC and cannot transmit to a
missing peer. See the [complete firmware setup guide](algorithm/firmware/README.md)
for separate role builds/uploads, MAC pairing, the guarded synthetic command
test and troubleshooting. Live Python remains monitor-only.

Oil-transformer analysis now uses **IEEE C57.91-2011 conventional physics** or
the actual **Alliander IEC 60076-7** library. RC describes the separate DC rig;
Ridge remains the preserved baseline. [Physics documentation](model/PHYSICS.md)
defines equations, parameters, reference tests and domain/actuation limits.

```sh
python -m pip install -e './model[physics,ml,dev]' -e './algorithm[ui,dev]'
python -m grid_model compare-physics
python -m grid_model compare-detection
python -m grid_model calibrate-rc
```

## Setup and one-command demo

From repository root, in Windows PowerShell or Unix:

```sh
python -m venv .venv
```

Activate using `.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` on Unix. Then:

```sh
python -m pip install -e './model[dev]' -e './algorithm[ui,dev]'
python -m grid_algorithm simulate --scenario dual_overload --duration-s 1800 --speed 0
```

The single demo command runs RC forecasting, a mutable plant, validated fake bridge/controller, applied ACKs, electrical switch-off and gradual cooling. It writes `algorithm/runs/demo.sqlite` and prints a machine-readable summary. Rail 1 remains protected; no automatic restoration occurs. After installation, runtime needs no network.

## Train, replay, inspect and test

Copy the supplied synthetic package into `model/data/` and `algorithm/fixtures/` as documented in [DATA.md](DATA.md). Existing fixtures are preserved. Missing training inputs produce explicit errors; the RC demo still runs.

```sh
python -m grid_model inspect
python -m grid_model train --model ridge --output model/artifacts/ridge-retrained
python -m grid_model evaluate --artifact model/artifacts/ridge-demo --split test
python -m grid_algorithm simulate --artifact model/artifacts/ridge-demo --duration-s 1800
python -m grid_algorithm replay --speed 0 --dry-run
python -m streamlit run algorithm/dashboard/app.py --server.address 127.0.0.1
python -m grid_algorithm export --log algorithm/runs/demo.sqlite --output algorithm/runs/events.csv
python -m pytest model/tests algorithm/tests -q
```

For optional neural comparisons, install `python -m pip install -e './model[ml,dev]'`, then run `python -m grid_model train --model lstm --quick` and `python -m grid_model train --model transformer --quick`. Omit `--quick` for full training. Every subcommand supports `--help`.

## Project map

```text
model/       causal features, RC/persistence/Ridge/LSTM/Transformer, CLI,
             configuration, local data/artifacts and model tests
algorithm/   NDJSON, replay/live transport, plant/controller/bridge, policy,
             coordinator, SQLite/CSV, dashboard and integration tests
  firmware/  rig_controller (ESP32 A), bridge (ESP32 B), common protocol
```

[Model documentation](model/README.md) covers leakage prevention, metrics and fallback. [Algorithm documentation](algorithm/README.md) defines the protocol, dashboard, safety state machine and hardware checklist. [DELIVERABLES.md](DELIVERABLES.md) tracks checkpoints; [DATA.md](DATA.md) documents synthetic provenance. [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and [STRUCTURE.md](STRUCTURE.md) govern workflow and roles.

[Observed validation results](algorithm/VALIDATION.md) include model metrics,
closed-loop evidence and dry-run build sizes. `python algorithm/scripts/smoke.py`
runs an assertion-checked offline demo. Install PlatformIO with
`python -m pip install platformio` if `pio` is unavailable.

The latest [engineering report](algorithm/ENGINEERING_REPORT.md) covers the IEEE/IEC
architecture correction, 39.4% validation-recall diagnosis, separate detection
results, independent rail profiles and current hardware limits.

## Hardware remains disabled

```sh
pio run -d algorithm/firmware/rig_controller -e controller_esp32dev
pio run -d algorithm/firmware/bridge -e bridge_esp32dev
python -m grid_algorithm link-check --port YOUR_ESP32_B_PORT --duration-s 10
python -m grid_algorithm live --port YOUR_ESP32_B_PORT --baud 115200 --monitor-only
```

These build dry-run firmware and start monitor-only ingestion. They do not flash or actuate. Exact boards/pins, calibration, polarity, electrical ratings, real thresholds, independent thermal cutoff, emergency stop and hardware-team approval remain pending. Compile-time gates refuse unverified physical outputs. Never connect 12 V to ESP32 logic or shed MCU power.
