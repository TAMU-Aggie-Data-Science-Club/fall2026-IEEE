# ESP-NOW migration audit and validation — 2026-11-17

Branch: `feature/espnow-two-board-integration`, based on `darsh`.
This is a new migration record. Earlier VALIDATION.md and ENGINEERING_REPORT.md
remain historical and have not been rewritten to imply wireless testing.

## Audit and implemented decisions

Reviewed project Markdown, Python algorithm/model tests and package definitions,
firmware entry points/shared protocol/configurations, CLI/dashboard and Actions.
Accessible reference PDF text was reviewed; the local MiKTeX extractor emitted
a log-directory permission warning. Older PDF/MQTT/UART suggestions are historical;
the explicit current task selects USB + ESP-NOW. The supplied fixture contract
and data are preserved.

The old firmware coupled `SIMULATED_IO` to transport: B did not forward with
mock I/O, and A routed its mock telemetry to local USB rather than the peer.
The physical watchdog also used last relay-command time, incorrectly treating a
healthy quiet link as disconnected. These were targeted migration changes.

The new implementation keeps laptop models/policy/logs over canonical USB NDJSON,
with B handling wireless fragmentation and A alone producing applied ACKs. Radio,
sensor simulation and physical output enable are independent. Default binaries
enable ESP-NOW and mock sensors with physical outputs disabled and hardware
verification false. Unspecified peers are reported; no fictional MAC is installed.
Physical images additionally require real sensors, encryption, verified mappings,
limits/polarity/calibration and local runtime arming. No model or threshold fit
was changed. Oil-transformer models remain analysis-only.

The pinned installed framework's actual `esp_now.h` confirms the older callback
signatures and 250-byte payload ceiling. Implementation follows
[Espressif ESP-IDF 4.4 ESP-NOW documentation](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-reference/network/esp_now.html),
not a newer Arduino-core signature. Shared transport is header-only so both
independent projects compile the same implementation. Explicit WiFi includes in
the entry points correct PlatformIO dependency discovery for the external header.

## Code and operator handoff

```text
algorithm/firmware/
  README.md                         full power/pairing/build/upload/bench guide
  common/
    protocol.h                      strict complete NDJSON parsing/framing
    espnow_packet.h                 portable bounded binary codec/reassembler
    espnow_transport.h              pinned-SDK callback/queue/radio adapter
    radio_config.h                  independent radio/peer/security defaults
    tests/packet_native.cpp         actual production codec native checks
  bridge/                           bridge_esp32dev project
  rig_controller/                   controller_esp32dev project
  scripts/
    flash.ps1                       explicit role/port, error propagation
    list_ports.py                   read-only discovery
    wireless_smoke.py               read-only or guarded simulated OFF only
    native_tests.py                 g++/clang++/local Zig native runner
algorithm/src/grid_algorithm/
  espnow.py, wireless_sim.py         matching host reference/virtual radio path
  transport.py, cli.py               unchanged USB protocol; status/link-check
  coordinator.py                    boot-token reset handling/domain safety
  dashboard_state.py                 separate source/serial/radio/telemetry age
algorithm/tests/                     wireless/native/status/bench regressions
```

Root/algorithm/model READMEs, ENTROPY_AGENTS.md and deliverables now identify the
selected wireless topology. Original fixture/PDF and dated scientific reports
remain source/history documents. CI adds independent role compilation and native
codec checks; no remote CI execution, upload or physical test is claimed.

## Observed verification

- Initial wireless/native run: **18 passed**, including byte-for-byte C++/Python
  golden vectors at 4, 700 and 2048 bytes. Native tests compiled and executed the
  production portable codec with the workspace-local Zig compiler.
- Intermediate full run: **87 passed in 65.61s**. Final expanded run is recorded
  as **92 passed in 52.70s**, including bench-tool, freshness and source checks.
- Full 1,800-sample closed loop now traverses the virtual radio envelope, received
  two controller ACKs, shed only eligible branches and measured gradual cooling.
  Rail 2: OFF at 81s / 38.367°C, then 36.253°C after 60s. Rail 3: OFF at 141s /
  41.720°C, then 39.307°C after 60s. Current was zero after both operations.
  **Zero protected-rail sheds; zero automatic restores.**
- Passive replay processed **2,993 packets**, **zero generated commands**, and
  preserved the three recorded relay transitions, including scripted restoration.
- `compare-physics` and `compare-detection` completed in new ignored
  `model/reports/espnow-validation/` folders. Fifty-one model source/config/artifact
  and fixture file fingerprints matched the pre-migration snapshot. No original
  benchmark/artifact/fixture was overwritten. No unrelated model training ran;
  detector fitting occurs only inside the explicitly required comparison command.
- Syntax compilation passed. PowerShell's parser accepted `flash.ps1` without
  executing an upload. Role/port binding is explicit; no port is persisted.
- `link-check` against a nonexistent port safely reported serial failure, stale
  telemetry, no frames and `physical_verification:false`; no commands were sent.
  Port enumeration found no accessible serial ports during validation.

Tests cover sizes/fragments/reordering/duplicates/CRC/expiry/capacity/peer/version,
malformed JSON, incomplete commands, packet loss and recovery, same-ID retries,
lost/rejected ACKs, reboot while pending, serial reconnection and old controller
boot tokens. A bridge heartbeat cannot refresh the controller telemetry timestamp.
The guarded bench helper refuses real or unverified I/O without writing a command.
Existing physics, model-domain, protected-rail, policy and dashboard checks remain.

## Firmware builds and blockers

- Controller target `controller_esp32dev`: **SUCCESS** after WiFi dependency
  discovery was corrected. Final strict-parser build used **59,844 B RAM** and
  **760,901 B flash**, with simulated sensors and physical outputs disabled.
  ArduinoJson emitted containsKey deprecation warnings; the image built.
- Bridge target `bridge_esp32dev`: **SUCCESS**, using **60,504 B RAM** and
  **753,825 B flash**. The initial build failed WiFi dependency discovery; the
  entry-point include correction resolved it. One rebuild request was rejected;
  after the operator explicitly authorized the compile-only check again, it ran
  successfully. ArduinoJson containsKey deprecation warnings remain nonfatal.

No attempt was made to bypass the rejected rebuild approval. Both independent
role builds are now observed successful; independent CI jobs are also supplied.
Compilation is distinct from
upload, pairing, RF delivery, protocol bench verification and commissioning.

## Hardware and security limits

No physical upload, actual MAC discovery/pairing, RF-loss measurement, sensor,
thermal calibration or relay actuation was performed. Required next operator
steps are in [firmware/README.md](firmware/README.md): confirm exact boards and
ports, flash each explicit role, record actual station MACs, provision matching
peer/channel/keys, and bench-test with all relay wiring disconnected. A uses
independent approved power; B stays on laptop USB. No inter-board UART is used.

CRC32 and source-MAC filtering are not cryptographic authentication. Encryption
keys must be provisioned locally and not committed. The heartbeat watchdog uses
valid peer traffic, not relay-command frequency. Lost links/reboots never restore
physical loads. Real GPIO, ADC/sensor calibration, relay polarity/ratings,
temperature/current limits, fuses, independent cutoff/emergency stop and
hardware-team/faculty approval remain pending. The radio cannot replace them.
