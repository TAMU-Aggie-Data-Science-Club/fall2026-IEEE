# IEEE × ADSC — Synthetic ESP32 Grid Thermal Demo Data

**Purpose:** immediate software development without physical ESP32 boards, thermal sensors, or relay hardware.
**Data status: ALL SENSOR READINGS, FORECASTS, AND COMMANDS ARE SYNTHETIC.** This is not collected ESP32 data, not calibrated to an actual power transformer, and not a pretrained IEEE model output. Generated with a simplified first-order RC heat accumulation/cooling emulator, with plausible measurement noise and event timing. No IEEE C57.91 equations are used to generate these values. Do not treat threshold values as engineering safety limits.

## Assumed architecture

```
12 V low-voltage demo branches (rail_1, rail_2, rail_3)
   |  temperatures + currents + downstream rail voltages
ESP32 A (esp32_rig_01): samples sensors, actuates relays,
                        enforces local safety policy
   |  ESP-to-ESP UART or other *chosen later* transport
ESP32 B (esp32_bridge_01): forwards telemetry and commands
   |  USB serial
Laptop: parses samples -> forecast -> sends SET_RAIL_ENABLED command
   |  reverse path: laptop -> ESP32 B -> ESP32 A -> acknowledgement
```

All three "rails" here mean independently controlled **12 V load branches**, not the ESP32's 3.3 V or 5 V logic supply. Never interrupt MCU power to shed a demo load. Assumed 12 V, 5 A supply; do not extrapolate from the synthetic thermal data to real electrical safety.

## The CSV files

| File | Audience | Description |
|---|---|---|
| `esp32_telemetry_replay.csv` | Embedded / algorithm team | 2,993 rows spanning 50 minutes, ~1 Hz. Each row is one controller telemetry packet, wide format with three branches, DC current, voltage, hotspot temperature, relay states, uptime, packet sequence, fault flags. Has intentionally dropped packets and occasional missing temperatures. |
| `esp32_control_commands.csv` | Embedded / algorithm team | 3 synthetic laptop/bridge requests (shed and optional manual restore). These are **scripted**, not the result of an actual trained model. |
| `esp32_control_acks.csv` | Embedded / algorithm team | 3 controller acknowledgments, matched by `command_id`; demonstrates APPLIED relay state and round-trip command tracing. |
| `model_training_timeseries.csv` | ML / model team | 194,400 long-format records: scenario × second × rail, 36 fully simulated unmitigated trajectories, with 60s / 300s forecast targets and threshold-crossing labels. |
| `model_training_scenarios.csv` | ML / model team | 36 scenario definitions, per-scenario `train`/`val`/`test` assignments, peak temperature and stress descriptions. |
| `rail_config.csv` | Both teams | Prototype thresholds, synthetic rail roles, permitted load-shedding policy, sensor examples. Confirm actual pins, units, calibration, topology and thresholds with IEEE hardware before deployment. |

## Demo parameters — editable assumptions, NOT industry transformer limits

- Sampling: 1 Hz, UTC ISO 8601 timestamps, milliseconds in ESP32 `uptime_ms`. **Production note:** ESP32 without NTP/RTC usually only knows monotonic uptime; the laptop should attach UTC receive timestamps, or synchronize clock time explicitly.
- Three simulated 12 V load branches; loads normally about 0.4–0.8 A, overloaded branch roughly 1.7–1.8 A.
- Hot-spot sensor equivalent: DS18B20, roughly 0.0625 °C quantization; ambient °C; temperature recording can be blank if a reading is missing.
- Current sensor: DC-capable ACS712 **assumed**; direct CT clamp sensors normally require AC, not DC.
- Sensor voltage values are measured **after** the rail switch, therefore ~0 V when a rail is disabled; shared bus voltage remains ~12 V.
- Prototype warning threshold: 70 °C; critical threshold: 80 °C. These are demo-only.
- `rail_1` is protected (`shed_allowed=0`); `rail_2` and `rail_3` may be auto-shed. ESP32 A must enforce policy even if the laptop makes a bad decision.
- CSV `fault_flags` uses pipe-delimited strings. Missing temperatures are blank (not fabricated zeros). Packet sequence numbers can skip; do **not** assume contiguous rows.
- Synthetic commands happen at timestamp + 0.200 s; ACKs follow within about 85–150 ms. At 1 Hz, telemetry can reflect applied changes in the same second. No serial protocol is actually executed in these examples.

## ML team quick start

1. Read `model_training_timeseries.csv`, group by `scenario_id` + `rail_id`, sort by `elapsed_s`; never sort all rails as a single sequence.
2. Use historical observed ambient, voltage, current, power, and hotspot temperature. Use a rolling 300–600 s input window with a stride if training recurrent or attention models.
3. Predict `target_hotspot_temp_plus_60s_c`, `target_hotspot_temp_plus_300s_c`, or `target_crosses_80c_next_300s`. The targets are generated from noise-free future simulated thermal states.
4. Blank forecast labels at the end of a scenario mean the full look-ahead horizon is unavailable. `target_time_to_80c_within_600s` uses -1 for **no threshold crossing within 600 s**, and blank for a truncated horizon; -1 does not mean "never".
5. Split by `scenario_id` using `data_split`, not randomly by timestamp/row (which would leak highly correlated neighboring observations).
6. `sensor_valid=0` means observed current/voltage/temperature values are blank. Handle or filter intentionally.
7. **Important:** these data use *unmitigated* load scenarios; the replay CSV has interventions. Do not train a no-intervention forecast against already mitigated outcomes without explicitly modeling actions. Actual transformer parameter estimation and validation against IEEE C57.91 or IEC 60076-7 are separate, later steps.

## Embedded / algorithm team quick start

1. Replay the rows of `esp32_telemetry_replay.csv` in timestamp order as if receiving one telemetry frame per second from ESP32 A via ESP32 B.
2. On each record validate `packet_seq`, timestamp freshness, sensor values/ranges, `fault_flags`, and rail states; use fail-safe behavior for sensor faults or disconnected host.
3. Convert the selected model's output into a **request**; use `rail_id`, requested enabled state, reason and unique `command_id` as in `esp32_control_commands.csv`.
4. Send requests laptop -> ESP32 B -> ESP32 A; ESP32 A validates `shed_allowed`, applies its relay, and replies with `status` plus `command_id` as in `esp32_control_acks.csv`.
5. Never auto-enable a shed load solely on falling temperature. The example manual restore is an *authorized operator event*.
6. Add timeout/retry, command de-duplication, safe defaults, over-current protection, independent local thermal cutoff, and physical emergency stop before real hardware use. Prevent relay chatter with hysteresis and minimum off time.

## Suggested newline-delimited JSON for the actual serial interface

The CSV files are offline development fixtures; ESP32-to-ESP32 and ESP32-to-laptop communication is generally easier as **one JSON record per line**, framed by `\n`:

Telemetry example:
```json
{"type":"telemetry","seq":5001,"uptime_ms":0,"ambient_temp_c":26.1,"rails":[{"id":"rail_1","v":12.0,"a":0.62,"hotspot_c":35.1,"enabled":1},{"id":"rail_2","v":12.0,"a":0.52,"hotspot_c":36.8,"enabled":1},{"id":"rail_3","v":12.0,"a":0.62,"hotspot_c":37.2,"enabled":1}]}
```
Laptop/bridge command example:
```json
{"type":"command","command_id":"CMD-0001","rail_id":"rail_2","action":"SET_RAIL_ENABLED","enabled":0,"reason":"PREDICTED_OVERHEAT_180S"}
```
ESP32 A acknowledgement example:
```json
{"type":"ack","command_id":"CMD-0001","rail_id":"rail_2","status":"APPLIED","enabled":0}
```

All numeric units are included in CSV headers. The serial JSON schema above is a **proposal**, not a confirmed firmware wire format; coordinate both software teams and the IEEE hardware team before coding against it. USB provides power/data to ESP32 B; ESP32 A and the 12V load branches need their own properly regulated low-voltage supply. Two ESP32 UARTs need **common ground and matching 3.3 V logic levels**, or use another agreed link such as ESP-NOW/Wi-Fi.

## Replay controls and acceptance checks

- Each model scenario is a distinct episode, but timestamps run on different UTC dates to prevent duplicate global times.
- For tests, pause/accelerate playback; never tie the model pipeline to actual wall-clock time.
- Expected closed-loop command IDs and events are in commands/ACK CSVs. Forecast values are **synthetic stand-ins for a model output**, not independently validated predictions.
- Maintain exact `command_id` matching and ensure `SET_RAIL_ENABLED` is idempotent to make retransmissions safe.

## Generation details

- Fixed random seeds; simplified thermal ODE: dT/dt = (T_ambient + R_thermal × P - T) / tau with independent stochastic noise.
- Power approximately V × I with 12 V bus droop and switch branch voltage drop.
- Actual measured thermal response has heat-up/cool-down inertia; sensor readouts are noisy, and quantized for DS18B20-like readings.
- The environment, component placement, DS18B20-to-winding relation, actual heater transfer function, and 12V supply behavior will have to be established with real hardware data.
