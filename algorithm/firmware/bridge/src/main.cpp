#include <Arduino.h>
#include "hardware_config.h"
#include "../../common/protocol.h"

HardwareSerial rigLink(2);
LineReader upstream, downstream;
uint32_t heartbeat = 0, forwarded = 0;
void setup() {
  Serial.begin(115200);
#if !SIMULATED_IO
  rigLink.begin(115200, SERIAL_8N1, UART_RX, UART_TX);
#endif
}
void loop() {
  upstream.poll(Serial, [](JsonDocument &doc, const char *body) {
    if (doc["type"] != "command" || doc["destination"] != "esp32_rig_01") return;
#if !SIMULATED_IO
    rigLink.println(body); ++forwarded;
#else
    JsonDocument status; status["v"] = 1; status["type"] = "bridge_status";
    status["source"] = "esp32_bridge_01"; status["dry_run"] = true;
    status["command_id"] = doc["command_id"]; status["forwarded"] = false; emit(status, Serial);
#endif
  });
#if !SIMULATED_IO
  downstream.poll(rigLink, [](JsonDocument &doc, const char *body) {
    String type = doc["type"] | "";
    if ((type == "telemetry" || type == "ack" || type == "diagnostic") && doc["source"] == "esp32_rig_01") { Serial.println(body); ++forwarded; }
  });
#endif
  if (millis() - heartbeat >= 1000) {
    heartbeat = millis(); JsonDocument doc; doc["v"] = 1; doc["type"] = "bridge_status";
    doc["source"] = "esp32_bridge_01"; doc["uptime_ms"] = heartbeat;
    doc["dry_run"] = bool(SIMULATED_IO); doc["forwarded"] = forwarded;
    doc["parse_errors"] = upstream.errors + downstream.errors; emit(doc, Serial);
  }
  delay(1);
}
