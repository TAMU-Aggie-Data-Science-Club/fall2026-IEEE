#include <Arduino.h>
#include <WiFi.h> // visible to PlatformIO's dependency finder for the shared radio header
#include "hardware_config.h"
#include "../../common/protocol.h"
#include "../../common/espnow_transport.h"
//#error VERIFY_THIS_IS_THE_CORRECT_MAIN_CPP

EspNowTransport radio(gridradio::kBridge);
LineReader upstream;
uint32_t heartbeat = 0;
// void setup() {
//   // Serial.begin(115200);
//   // radio.begin(); radio.status(Serial);
//   // Serial.println("ESP32 is active");
  
// }
void setup() {
    Serial.begin(115200);
    delay(1500);

    Serial.println("STEP 1: ESP32 started");

    Serial.println("STEP 2: Initializing ESP-NOW");
    radio.begin();

    Serial.println("STEP 3: ESP-NOW initialization returned");
    radio.status(Serial);

    Serial.println("STEP 4: ESP32 bridge is active!");
}
void loop() {
  upstream.poll(Serial, [](JsonDocument &doc, const char *body) {
    if (doc["type"] != "command" || doc["destination"] != "esp32_rig_01") return;
    uint8_t bytes[MAX_LINE]; const size_t n=strlen(body);
    bool queued=false;
    if (n+1<=MAX_LINE) { memcpy(bytes,body,n); bytes[n]='\n'; queued=radio.sendRaw(bytes,n+1); }
    JsonDocument status; status["v"]=1; status["type"]="bridge_status"; status["source"]="esp32_bridge_01";
    status["event"]="command_queued"; status["command_id"]=doc["command_id"]; status["queued"]=queued;
    status["controller_applied"]=false; emit(status,Serial);
  });
  radio.poll([](JsonDocument &,const char *body,size_t length) {
    Serial.write(reinterpret_cast<const uint8_t *>(body),length); // preserve exact reassembled NDJSON
  });
  if (millis() - heartbeat >= 1000) {
    heartbeat = millis(); radio.heartbeat(); radio.status(Serial,upstream.errors);
  }
  delay(1);
}
