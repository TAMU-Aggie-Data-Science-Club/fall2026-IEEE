# Algorithm and embedded team

Laptop forecasting → deterministic policy → ESP32 B bridge → ESP32 A local
interlocks → independently switched 12 V demo branch. Never shed MCU power.
All supplied fixtures and virtual runs are **SYNTHETIC / DEMO ONLY**.

Current physical topology: **laptop USB ↔ B ↔ ESP-NOW unicast ↔ A**. No
inter-board UART is used. Firmware sensor simulation, radio enable and physical
output enable are independent. The [firmware guide](firmware/README.md) is the
operator reference for role-specific builds/uploads, peer MAC/channel/security,
independent A power, packet layout, safe bench tests and commissioning gates.

The architecture correction adds oil-transformer physics in the model team and
explicit model/hardware domain gating here. The dashboard selects IEEE C57.91,
Alliander IEC, calibrated RC or the preserved Ridge benchmark. Oil models operate
only in **Oil-transformer analysis**, never on demo telemetry or relay controls.
The original three-branch pipeline and all local safety interlocks remain.
See [model/PHYSICS.md](../model/PHYSICS.md) and the engineering report.

The rig now has independent initial temperatures, currents, overload onset times,
load ripple, thermal resistance and time constants per branch. Shared bus droop
is retained. Fitted RC calibration can be supplied with `--model calibrated_rc
--calibration model/artifacts/rc-calibration/calibration.json`; current fits are
synthetic, not verified physical calibration. Historical validation results from
the earlier identical-rail emulator remain in VALIDATION.md as a dated record.

## Run from repository root (PowerShell or Unix)

```sh
python -m pip install -e './model[dev]' -e './algorithm[ui,dev]'
python -m grid_algorithm simulate --scenario dual_overload --duration-s 1800 --speed 0
python -m grid_algorithm simulate --artifact model/artifacts/ridge-demo --duration-s 1800
python -m grid_algorithm replay --data algorithm/fixtures/esp32_telemetry_replay.csv --speed 0 --dry-run
python -m grid_algorithm export --log algorithm/runs/demo.sqlite --output algorithm/runs/events.csv
python -m streamlit run algorithm/dashboard/app.py --server.address 127.0.0.1
python -m grid_algorithm live --port YOUR_ESP32_B_PORT --baud 115200 --monitor-only
```

Simulation is a mutable plant, not playback of labeled outcomes. Commands drop
current/downstream voltage; stored heat decays gradually. Scenarios: `normal`,
`ramp`, `abrupt_overload`, `hot_ambient`, `dual_overload`. Seeded noise and virtual
time make behavior repeatable; UUID command IDs intentionally differ between
runs. Final JSON reports actual ACKs, shed times, 60s cooling, final temperatures,
protected-rail sheds and automatic restores.
The virtual bridge now fragments/reassembles the same bounded radio envelope as
firmware before invoking the virtual controller; live USB remains unaware of
fragments. Reordering/loss/duplicates/CRC and reboot cases are regression-tested.

Passive replay preserves all 2,993 packets and recorded transitions, including
the scripted manual restore. It generates no commands. `--speed 0` uses virtual
time; positive speed sets a playback factor; `--limit`/`--start-offset` work.
Live ingestion uses monotonic laptop arrival time, UTC receive audit time and
bounded reconnect backoff. Reboot clears windows/pending commands and disarms
the session; wrapping sequence/uptime, dropped/duplicate packets and stale data
are tracked. Synthetic CSV UTC dates do not determine playback freshness.

## Policy and safety

`fixtures/rail_config.csv` governs warning/critical values, priority and shedding
permission. Rail 1 is protected; only rails 2/3 auto-shed. Demo thresholds are
not physical safety ratings. `configs/demo.yaml` is JSON-compatible YAML for
persistence, cooldown, ACK timeout/retry count, freshness, minimum off-time and
restoration hysteresis. Global `--config PATH` precedes the subcommand.

Two consecutive valid +300s warning forecasts (or measured warnings) request OFF.
Missing/bad sensors or global faults suppress predictive operations; independent
controller-local temperature/current/sensor cutoffs remain active for eligible
loads. States: `ON`, `SHED_REQUESTED`, `SHED_CONFIRMED`, `RESTORE_REQUESTED`,
`FAULT`, initial `UNKNOWN`. A matching successful ACK plus subsequent matching
telemetry completes a transition. Contradiction, stale data or exhausted retries
fault the state. Retries keep identical ID/body with bounded exponential backoff.
Queue size is bounded by rail count. No toggles and no automatic reenable.

The independent SQLite WAL dashboard shows observations, forecasts, ambient,
thresholds, relay states, faults, freshness and command/ACK history. Choose
**Interactive virtual rig**, advance time and supply operator identity plus
explicit consent for virtual restoration. UI and controller require safe sensors,
temperature, confirmed off and minimum off-time. Actions record operator identity.
A dashboard failure cannot stop the CLI or local controller. No physical or
remote restoration endpoint is exposed.

Live mode remains monitor-only with no override in this uncommissioned release.
Transport refuses sends by default. After hardware approval, a reviewed explicit
operator arming workflow is required before enabling physical laptop control.

## Definitive wire contract v1

UTF-8 NDJSON, one object/newline, maximum **2048 bytes including newline**,
configurable 115200 baud 8N1. All messages: integer `v:1`, nonempty string `source`,
string `type`. JSON uses true/false; CSV uses 0/1. Nonfinite numbers are rejected.
Sensor null means unavailable, never fabricated zero.

| Type | Fields |
|---|---|
| `telemetry` | `source:esp32_rig_01`, uint32 `seq`, uint32 `uptime_ms`, nullable `ambient_temp_c`/`bus_voltage_v`, unique nonempty `rails`, string-array `fault_flags`, nullable `last_applied_command_id` |
| rail | `id`, nullable `v` (0–30 V), `a` (0–10 A), `hotspot_c` (-55–125°C), boolean `enabled`/`sensor_valid`; valid observations cannot be null; optional controller-authoritative `safe_to_restore` |
| `command` | `command_id`, `source:laptop`, `destination:esp32_rig_01`, `action:SET_RAIL_ENABLED`, `rail_id`, boolean `enabled`, `reason`; restore also requires local `operator` identity |
| `ack` | matching `command_id`, `source:esp32_rig_01`, `rail_id`, `status`, actual boolean `enabled`, integer `controller_uptime_ms` |
| `bridge_status`/`diagnostic` | explicit separate types ignored by policy; never raw debug text |

ACK statuses: `APPLIED`, `ALREADY_APPLIED`, `REJECTED_PROTECTED`,
`REJECTED_UNARMED`, `REJECTED_UNSAFE`, `REJECTED_INVALID`, `ERROR`.
Receipt at the bridge is not application at the controller. Real/fake links use
the same Python protocol. Unknown version/type, duplicate rails/JSON keys,
overlength, malformed and out-of-range frames are rejected. The parser recovers
at the next newline. The bridge never invents a controller reading or relay state.

## Firmware

```sh
pio run -d algorithm/firmware/rig_controller -e controller_esp32dev
pio run -d algorithm/firmware/bridge -e bridge_esp32dev
```

Defaults: generic `esp32dev` (configurable), Arduino, `SIMULATED_SENSORS=1`,
`ENABLE_ESPNOW=1`, `PHYSICAL_OUTPUTS=0`, hardware verification false. Unicast peer
addresses are supplied only in ignored local configuration. Missing peers produce
diagnostics rather than fictional addresses or broadcast actuation. Full NDJSON
messages are fragmented into ≤220-byte packets and validated after reassembly.
DS18B20 conversion is asynchronous; real DC ACS712/voltage adapters still require
approved GPIO and measured calibration. USB output on A is local diagnostics;
telemetry and controller ACKs go over ESP-NOW to B. Heartbeat freshness, not
absence of relay commands, supervises the radio link.
Physical outputs require verified GPIO/calibration/polarity, compile-time enable
and local runtime arming. Physical boot is off; no automatic reenergization.
Local faults/command-heartbeat loss cut eligible loads independently. Protected
load emergency behavior needs hardware approval. Firmware is no substitute for
fuses, emergency stop or an independent thermal cutoff.

Commissioning remains pending:

- [ ] Exact ESP32 A/B boards and safe independent supplies; observed station MACs, matching channel and secure peer provisioning.
- [ ] Sensor count/placement/addresses/pull-up, DC sensing and ADC calibration/noise.
- [ ] Relay/MOSFET ratings/polarity/default off, fuses, emergency stop, independent thermal cutoff.
- [ ] Approved real thresholds/heater/current limits and protected-load emergency behavior.
- [ ] Outputs-disconnected serial test, LED/dummy test, supervised low-power and faculty/hardware safety review.

Build success is not flashing or physical commissioning.
