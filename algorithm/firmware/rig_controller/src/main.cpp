#include <Arduino.h>
#include <WiFi.h>
#include "hardware_config.h"
#include "../../common/protocol.h"
#include "../../common/espnow_transport.h"
#if !SIMULATED_SENSORS
#include <OneWire.h>
#include <DallasTemperature.h>
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
#endif

EspNowTransport radio(gridradio::kController);
const char *ids[] = {"rail_1", "rail_2", "rail_3"};
bool enabled[3] = {false, false, false};
bool validSensor[3] = {false, false, false};
float temp[3] = {35, 35, 35}, current[3] = {0, 0, 0}, voltage[3] = {0, 0, 0};
float ambient = 26, bus = 12;
uint32_t offAt[3] = {0, 0, 0};
uint32_t lastSample = 0, seq = 0, lastStatus = 0;
bool linkWasHealthy = false;
String lastId;
bool armed = false;
struct Remember { String id, body; int rail = -1; bool enabled = false; };
Remember recent[32]; size_t nextRecent = 0;

void setRail(int i, bool state) {
  enabled[i] = state;
  if (!state) offAt[i] = millis();
#if PHYSICAL_OUTPUTS
  digitalWrite(RELAY_PINS[i], state == ACTIVE_HIGH ? HIGH : LOW);
#endif
}
bool safeRestore(int i) {
  return validSensor[i] && temp[i] < WARNING_C[i] - 5 && millis() - offAt[i] >= MIN_OFF_MS;
}
void ack(JsonDocument &request, int rail, const char *status) {
  JsonDocument reply;
  reply["v"] = 1; reply["type"] = "ack"; reply["source"] = "esp32_rig_01";
  reply["command_id"] = request["command_id"]; reply["rail_id"] = request["rail_id"];
  reply["status"] = status; reply["enabled"] = rail >= 0 ? enabled[rail] : false;
  reply["controller_uptime_ms"] = millis();
  reply["physical_actuation"] = bool(PHYSICAL_OUTPUTS); reply["simulated_sensors"] = bool(SIMULATED_SENSORS);
  radio.send(reply);
}
void handle(JsonDocument &doc, const char *body) {
  if (doc["type"] != "command") return;
  int rail = -1;
  for (int i = 0; i < 3; ++i) if (doc["rail_id"] == ids[i]) rail = i;
  if (rail < 0 || doc["destination"] != "esp32_rig_01") { ack(doc, rail, "REJECTED_INVALID"); return; }
  const String id = doc["command_id"].as<String>();
  for (const auto &entry : recent) if (entry.id == id) {
    ack(doc, rail, entry.body != body ? "REJECTED_INVALID" :
        enabled[rail] == entry.enabled ? "ALREADY_APPLIED" : "REJECTED_UNSAFE"); return;
  }
  const bool requested = doc["enabled"];
  if (!SHED_ALLOWED[rail]) { ack(doc, rail, "REJECTED_PROTECTED"); return; }
  if (!armed) { ack(doc, rail, "REJECTED_UNARMED"); return; }
  if (!validSensor[rail] || (requested && (!safeRestore(rail) || !nonempty(doc["operator"]) ||
      !String(doc["reason"].as<const char *>()).startsWith("MANUAL_RESTORE")))) {
    ack(doc, rail, "REJECTED_UNSAFE"); return;
  }
  const bool same = enabled[rail] == requested;
  if (!same) setRail(rail, requested);
  recent[nextRecent].id = id; recent[nextRecent].body = body;
  recent[nextRecent].rail = rail; recent[nextRecent].enabled = requested;
  nextRecent = (nextRecent + 1) % 32;
  lastId = id;
  ack(doc, rail, same ? "ALREADY_APPLIED" : "APPLIED");
}
void sample(float dt) {
#if SIMULATED_SENSORS
  for (int i = 0; i < 3; ++i) {
    current[i] = enabled[i] ? (i == 0 ? .6f : 2.f) : 0;
    voltage[i] = enabled[i] ? 11.9f : 0;
    const float eq = ambient + (2.9f + .3f*i) * current[i] * voltage[i];
    temp[i] = eq + (temp[i] - eq) * expf(-dt / (280.f+40.f*i)); validSensor[i] = true;
  }
#else
  // Asynchronous 12-bit conversion; hardware sensor index/address map needs approval.
  ambient = sensors.getTempCByIndex(0);
  bus = BUS_PIN >= 0 ? analogReadMilliVolts(BUS_PIN) / 1000.f * DIVIDER_RATIO : NAN;
  for (int i = 0; i < 3; ++i) {
    temp[i] = sensors.getTempCByIndex(i + 1);
    current[i] = CURRENT_PINS[i] >= 0 ? (analogReadMilliVolts(CURRENT_PINS[i]) / 1000.f - CURRENT_ZERO_V[i]) / CURRENT_V_PER_A[i] : NAN;
    voltage[i] = VOLTAGE_PINS[i] >= 0 ? analogReadMilliVolts(VOLTAGE_PINS[i]) / 1000.f * DIVIDER_RATIO : NAN;
    validSensor[i] = isfinite(temp[i]) && temp[i] >= -55 && temp[i] <= 125 && temp[i] != 85 &&
      isfinite(current[i]) && current[i] >= 0 && current[i] <= 10 && isfinite(voltage[i]) && voltage[i] >= 0 && voltage[i] <= 30 &&
      isfinite(ambient) && ambient >= -55 && ambient <= 125 && isfinite(bus) && bus >= 0 && bus <= 30;
  }
  sensors.requestTemperatures();
#endif
}
void protect() {
  for (int i = 0; i < 3; ++i) if (SHED_ALLOWED[i] && enabled[i] &&
      (!validSensor[i] || temp[i] >= CRITICAL_C[i] || current[i] > 3 ||
       (PHYSICAL_OUTPUTS && !radio.healthy(millis())))) setRail(i, false);
}
void telemetry() {
  JsonDocument doc; doc["v"] = 1; doc["type"] = "telemetry"; doc["source"] = "esp32_rig_01";
  doc["seq"] = ++seq; doc["uptime_ms"] = millis();
  doc["controller_session"] = radio.bootSession();
  doc["simulated_sensors"] = bool(SIMULATED_SENSORS); doc["physical_outputs_enabled"] = bool(PHYSICAL_OUTPUTS);
  if (isfinite(ambient)) doc["ambient_temp_c"] = ambient; else doc["ambient_temp_c"] = nullptr;
  if (isfinite(bus)) doc["bus_voltage_v"] = bus; else doc["bus_voltage_v"] = nullptr;
  auto faults = doc["fault_flags"].to<JsonArray>(); auto rails = doc["rails"].to<JsonArray>();
  for (int i = 0; i < 3; ++i) {
    auto r = rails.add<JsonObject>(); r["id"] = ids[i]; r["enabled"] = enabled[i]; r["sensor_valid"] = validSensor[i];
    if (validSensor[i]) { r["v"] = voltage[i]; r["a"] = current[i]; r["hotspot_c"] = temp[i]; }
    else { r["v"] = nullptr; r["a"] = nullptr; r["hotspot_c"] = nullptr; faults.add(String("SENSOR:") + ids[i]); }
    r["safe_to_restore"] = safeRestore(i);
    if (!SHED_ALLOWED[i] && temp[i] >= WARNING_C[i]) faults.add("PROTECTED_LOAD_ALARM");
  }
  if (lastId.length()) doc["last_applied_command_id"] = lastId; else doc["last_applied_command_id"] = nullptr;
  radio.send(doc);
}
void setup() {
  Serial.begin(115200);
  radio.begin(); radio.status(Serial);
#if SIMULATED_SENSORS && !PHYSICAL_OUTPUTS
  armed = true;
  for (int i = 0; i < 3; ++i) { enabled[i] = true; validSensor[i]=true; } // virtual loads only
  sample(0); // initialize mock validity before the first local protection pass
#else
  sensors.begin(); sensors.setWaitForConversion(false); sensors.requestTemperatures();
#if PHYSICAL_OUTPUTS
  for (int pin : RELAY_PINS) { digitalWrite(pin, ACTIVE_HIGH ? LOW : HIGH); pinMode(pin, OUTPUT); }
  pinMode(ARM_PIN, INPUT_PULLUP);
#endif
#endif
}
void loop() {
#if PHYSICAL_OUTPUTS
  armed = HARDWARE_VERIFIED && digitalRead(ARM_PIN) == LOW;
  if (!armed) for (int i = 0; i < 3; ++i) if (SHED_ALLOWED[i] && enabled[i]) setRail(i, false);
#endif
  radio.poll([](JsonDocument &doc,const char *body,size_t) { handle(doc,body); });
  const uint32_t now = millis();
  if (now - lastSample >= 1000) { sample((now - lastSample) / 1000.f); lastSample = now; protect(); telemetry(); radio.heartbeat(); }
  if (now-lastStatus>=2000) { lastStatus=now; radio.status(Serial); }
  bool healthy=radio.healthy(now);
  if (linkWasHealthy && !healthy) { JsonDocument fault; fault["v"]=1; fault["type"]="diagnostic"; fault["source"]="esp32_rig_01"; fault["event"]="link_lost"; fault["physical_outputs_enabled"]=bool(PHYSICAL_OUTPUTS); emit(fault,Serial); }
  linkWasHealthy=healthy;
  protect(); delay(1);
}
