# Two-board ESP-NOW firmware and operator handoff

**Current topology:** laptop Python models/policy/logs ↔ USB serial ↔ **ESP32 B**
bridge ↔ **ESP-NOW unicast** ↔ independently powered **ESP32 A** controller ↔
three 12 V demo branches. No router, campus Wi-Fi, Internet, inter-board UART,
or inter-board ground wire is required for the wireless link. Each board still
needs its own correctly regulated power and its own local electrical grounding.
Never connect 12 V directly to an ESP32 pin or logic supply.

The model runs on the laptop. B never predicts or operates outputs. A samples,
validates/deduplicates set-state requests, applies local interlocks and produces
ACKs reporting its state. A radio-send callback is **not** an applied ACK.
IEEE/IEC oil-transformer models remain analysis-only; DC rig control has separate
RC/Ridge domain gates. USB live mode is **monitor-only** throughout this migration.

## Safe default configuration

| Setting | Default | Meaning |
|---|---|---|
| `ENABLE_ESPNOW` | 1 | Actual wireless transport, independent of sensor mode |
| `SIMULATED_SENSORS` (A) | 1 | Synthetic temperatures/current/voltage, no sensor GPIO needed |
| `PHYSICAL_OUTPUTS` (A) | 0 | No relay GPIO initialization or writes |
| `HARDWARE_VERIFIED` (A) | false | Pin/calibration/polarity/safety approval not supplied |
| `ESPNOW_PEER_MAC` | empty | Prints actual own MAC; cannot send until explicit peer is configured |
| `ESPNOW_ENCRYPTION` | 0 | Unencrypted **disconnected-output bench** mode; whitelist is not authentication |
| Laptop live actuation | disabled | No `live` CLI override |

Virtual rails can change state and report APPLIED with `physical_actuation:false`.
That is not evidence of any physical switching. `simulated_sensors` and
`physical_outputs_enabled` are included in telemetry. Physical boot is off;
no automatic restoration follows a reset, recovery or cooldown. Protected rail 1
cannot be normally shed; local eligible-load protection remains independent of
laptop/model requests. Real thresholds remain unapproved.

## 1. Software and exact board identification

Install VS Code + its **PlatformIO IDE extension**, Python 3.11+, and the project
packages. No Arduino IDE is required. Run commands below from repository root:

```powershell
python -m pip install -e './model[physics,dev]' -e './algorithm[ui,dev]'
# If PlatformIO is not available through the VS Code PlatformIO terminal:
python -m pip install platformio
```

Read both module/board labels and confirm the manufacturer schematic/pinout. A
classic ESP32-WROOM/DevKit, ESP32-C3 and ESP32-S3 are not interchangeable board
targets. `esp32dev` is an explicitly provisional generic target, not a confirmed
hardware identity. Change `board = ...` in the role's `platformio.ini` when the
exact variant is known. Keep the compatible pinned platform unless an upgrade is
separately tested. Native-USB variants may need their documented USB build flags.

The pinned platform `espressif32@6.10.0` uses Arduino ESP32 2.0.17 / ESP-IDF 4.4.
Callbacks follow the inspected older signatures `(mac,data,len)` and
`(mac,status)`, not newer Arduino 3.x APIs. Wi-Fi is explicitly included from each
entry point so PlatformIO discovers the framework's WiFi library through the
shared header. All radio/codec code is shared header-only; no external-source
build-filter trick is required.

## 2. Discover and label ports

```powershell
python algorithm/firmware/scripts/list_ports.py
python -m serial.tools.list_ports -v
pio device list
```

In Windows Device Manager, inspect **Ports (COM & LPT)** and unplug/reconnect one
board at a time to identify its actual port. Label the physical boards **A** and
**B**. The COM5/COM6 examples below are placeholders; replace them with observed
ports. No port is stored in tracked configuration. A charge-only USB cable may
power a board without exposing a data port. Install only the driver appropriate
to the board's actual USB interface (e.g. CP210x, CH34x or native USB).

## 3. Independently build, upload and discover station MACs

Start with no relays/loads/sensors connected. Default binaries work without a
peer address and emit their actual station MAC in diagnostic JSON on local USB.

```powershell
pio run -d algorithm/firmware/bridge -e bridge_esp32dev
pio run -d algorithm/firmware/rig_controller -e controller_esp32dev

# Upload ONLY after checking which physical board is on each selected port:
.\algorithm\firmware\scripts\flash.ps1 -Role bridge -Port COM5
.\algorithm\firmware\scripts\flash.ps1 -Role controller -Port COM6

# Equivalent explicit PlatformIO uploads:
pio run -d algorithm/firmware/bridge -e bridge_esp32dev -t upload --upload-port COM5
pio run -d algorithm/firmware/rig_controller -e controller_esp32dev -t upload --upload-port COM6

pio device monitor --port COM5 --baud 115200
pio device monitor --port COM6 --baud 115200
```

The helper requires explicit valid role/port, prints project/environment/port,
and propagates failures. It never discovers a board and silently chooses it for
upload. Its PlatformIO fallback uses the current user's extension installation,
not a machine-specific path. Close a monitor with Ctrl+C before uploading or
opening Python on the same COM port. Two processes usually cannot own one Windows
COM port simultaneously.

Recognizable output (values below describe fields, not fabricated device values):

```text
B: {"v":1,"type":"bridge_status","source":"esp32_bridge_01",...,
    "transport":"espnow","local_mac":<ACTUAL_B_STA_MAC>,
    "link_initialized":true,"peer_configured":false,...}
A: {"v":1,"type":"diagnostic","source":"esp32_rig_01",...,
    "local_mac":<ACTUAL_A_STA_MAC>,"event":"link_status",...}
```

Actual output is one complete JSON object per line. Record the **station** MAC,
not a SoftAP or Bluetooth MAC. ROM boot text may precede application NDJSON; the
laptop framing parser discards malformed lines and resynchronizes.

## 4. Provision explicit unicast peers and common channel

```powershell
Copy-Item algorithm/firmware/bridge/include/peer_config.example.h algorithm/firmware/bridge/include/peer_config.h
Copy-Item algorithm/firmware/rig_controller/include/peer_config.example.h algorithm/firmware/rig_controller/include/peer_config.h
```

Edit the ignored local headers:

- B's `ESPNOW_PEER_MAC` = **A's actual station MAC**.
- A's `ESPNOW_PEER_MAC` = **B's actual station MAC**.
- Set `ESPNOW_CHANNEL` identically on both, using a locally permitted channel
  1–11. Default 1 is a bench assumption, not measured RF suitability.
- Rebuild and flash each role again with its own header and explicit port.

Zero, malformed, multicast and broadcast peer addresses are rejected. No device
addresses are invented in tracked configuration. Both boards use Wi-Fi station
mode on the same fixed channel without connecting to an AP. Pairing is local
configuration; automatic broadcast discovery/commands are intentionally absent.

For encrypted unicast, generate two independent 16-byte values locally:

```powershell
python -c "import secrets; print('PMK:', secrets.token_hex(16)); print('LMK:', secrets.token_hex(16))"
```

Put the same generated PMK/LMK on both local headers as 32 hex characters and set
`ESPNOW_ENCRYPTION 1`. Do not paste keys into issues/logs/commits. The header is
ignored, but compiled firmware contains provisioned secrets and must be handled
accordingly. No keys are logged. Invalid/missing/all-zero encryption keys fail
initialization. ESP-NOW CCMP provides cryptographic protection with provisioned
keys; a source-MAC whitelist and CRC32 alone do **not** authenticate a sender.
Physical-output builds require encryption plus independent hardware approval.

## 5. Independent power and wireless bench test

Keep B connected by USB to the laptop. A can use its own suitable USB supply or
the development board's approved regulated input; confirm the exact board's
power requirements. A does not require a laptop USB data connection in normal
wireless operation. Never power the 12 V loads through an ESP32 regulator. No
inter-board TX/RX wires are used. Keep all relays/heaters physically disconnected.

Healthy B output should report `peer_configured:true`, `peer_recent:true`, a
non-null `last_rx_age_ms`, and growing sent/received counters. A telemetry should
arrive through B with `source:"esp32_rig_01"`, three rails, increasing sequence,
`simulated_sensors:true`, `physical_outputs_enabled:false` and a boot-session ID.

```powershell
python -m grid_algorithm link-check --port COM5 --baud 115200 --duration-s 10
python -m grid_algorithm live --port COM5 --baud 115200 --monitor-only --log algorithm/runs/live.sqlite
```

These commands **never send a relay command**. In another terminal:

```powershell
python -m streamlit run algorithm/dashboard/app.py --server.address 127.0.0.1
```

Select the audit log `algorithm/runs/live.sqlite`. The UI separates serial
connection, wireless peer freshness, sensor mode, logical state and ACK history.
No radio-send or bridge-queued event is shown as a physically verified operation.

For one explicit simulated OFF request, stop other owners of B's port and run:

```powershell
python algorithm/firmware/scripts/wireless_smoke.py --port COM5
python algorithm/firmware/scripts/wireless_smoke.py --port COM5 --simulate-shed rail_2 --outputs-disconnected
```

The separate bench tool first requires fresh controller telemetry explicitly
reporting simulated sensors and disabled outputs. Otherwise it fails **without
sending**. It can only request OFF for rail 2 or 3, retries the same command ID
at most three times, and requires both a controller ACK with
`physical_actuation:false` and subsequent OFF telemetry. It never restores a
branch or enables live application actuation. Reload the mock firmware to reset
the virtual demonstration, or use the existing explicitly supervised restore
workflow in its appropriate software-only context.

## 6. Packet specification and bounded behavior

USB remains UTF-8 NDJSON v1, **2048 bytes including LF**. The laptop live driver
does not see wireless fragments. Radio application packets are at most **220
bytes** (28-byte header + 192-byte fragment), below ESP-NOW v1's 250-byte limit.

| Offset | Bytes | Little-endian field |
|---:|---:|---|
| 0 | 2 | ASCII `EG` magic |
| 2 | 1 | transport version 1 |
| 3 | 1 | sender role: A=1, B=2 |
| 4 | 1 | receiver role, the opposite role |
| 5 | 1 | flags, zero in v1 |
| 6 | 4 | sender's random nonzero boot session |
| 10 | 4 | nonzero message ID within boot |
| 14 | 2 | complete NDJSON length, 1–2048 |
| 16 | 1 | zero-based fragment index |
| 17 | 1 | fragment count, ceiling(length/192), at most 11 |
| 18 | 2 | exact fragment length |
| 20 | 4 | CRC32 of complete original NDJSON (IEEE polynomial, zlib-compatible) |
| 24 | 4 | target boot session; zero only for startup non-command traffic |
| 28 | ≤192 | original bytes |

Each side has two 2048-byte reassembly slots, fixed first-fragment deadlines of
1500ms, an eight-entry completed-ID cache, a 16-packet callback queue, and four
complete-message TX slots. Fragment order does not matter; duplicates are checked;
conflicting fragments, bad lengths/version/roles/CRC, unknown MACs and old target
boots cannot execute a partial command. Complete NDJSON is validated before
routing/application. Exact bytes are preserved upstream. Packet reassembly and
JSON work happen in the main loop, not high-priority Wi-Fi callbacks.

Only one fragment is in flight; the next waits for send completion. Errors drop
that bounded message; command-level retry retains `command_id` with a new radio
message ID. Missing send callbacks abort and reinitialize after bounded delay.
Initialization failures retry at 5s intervals. Status exposes actual initialization,
peer/channel/encryption, received age, counters, queue/parse/fragment errors,
reassembly timeouts, duplicate fragments and peer reset observations.

Heartbeats are verified complete frames every second, independently of relay
commands. Five seconds without valid peer traffic makes the radio link stale.
Physical eligible loads shut off on stale link/local sensor/temperature/current
faults; protected-load emergency behavior still requires approved hardware.
Recovery does not reenergize a load. Commands require the controller's current
boot token; valid peer boot changes retire old session tokens and queued work.
The laptop also clears pending operations/windows and disarms on controller boot
change even if uptime alone would be ambiguous. CRC/session counters are not
security substitutes for encrypted peers or physical emergency cutoffs.
Within a peer boot, delayed completed messages older than the most recent valid
message are dropped. This does not constrain fragment order within a message.
Commands lost to that conservative ordering rule can be retried with the same
logical command ID and a new transport message ID.

## 7. Offline verification and troubleshooting

```powershell
python -m pytest model/tests algorithm/tests -q
python -m grid_algorithm simulate --scenario dual_overload --duration-s 1800 --speed 0
python -m grid_algorithm replay --speed 0 --dry-run
python -m grid_model compare-physics --output model/reports/espnow-validation/physics
python -m grid_model compare-detection --output model/reports/espnow-validation/detection
python -m compileall -q model/src algorithm/src algorithm/dashboard
python algorithm/firmware/scripts/native_tests.py
```

The virtual bridge now uses the same binary envelope/reference specification.
Native tests compile the exact production C++ codec and compare bytes with Python,
including a 2048-byte message. Native checks need g++/clang++ or an optional
workspace-local Zig compiler; ESP32 compilation still uses PlatformIO.

- **No COM port:** data cable, USB port and correct board driver; identify in Device Manager.
- **Upload timeout:** right role/port/board, close all serial monitors, follow the board's BOOT/RESET download procedure, check stable power.
- **Peer configured false:** local header absent/empty/invalid; use the other board's actual station MAC and reflash the correct role.
- **Peer recent false:** check both supplies, actual peer MACs, same channel, matching encryption/key configuration, RF range/interference and diagnostic counters.
- **Initialization failure:** read `initialization_error`; verify channel, available memory, supported board/framework and key lengths. Do not disable safety gates to fix pairing.
- **Drops/CRC/timeouts:** inspect fragment/queue/send counters; reduce traffic/interference and use a clear common channel. Radio success does not mean command applied.
- **Stale telemetry with USB connected:** distinguish serial from radio status; A may be missing, rebooting, unpaired or reporting invalid sensors.
- **Port access denied:** close other monitor/Python processes; do not let two programs own the same port.

Compilation proves compiler compatibility; uploading proves flashing only;
observed telemetry/ACKs prove a protocol bench path only. None proves electrical
safety. Before any physical-output build, confirm exact boards, supply/grounding,
ADC/sensor mappings and calibration, relay polarity/default-off/current ratings,
fuses/independent thermal cutoff/emergency stop, real temperature/current/heater
limits, protected-rail emergency behavior, secure peer provisioning and supervised
hardware/faculty review. All remain pending. No hardware upload/pairing or relay
operation was performed as part of software migration validation.
