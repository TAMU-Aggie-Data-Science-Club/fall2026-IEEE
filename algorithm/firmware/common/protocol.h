#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <math.h>

constexpr size_t MAX_LINE = 2048;
inline bool nonempty(JsonVariantConst v) {
  return v.is<const char *>() && strlen(v.as<const char *>()) > 0 && strlen(v.as<const char *>()) <= 128;
}
inline bool bounded(JsonVariantConst v, float low, float high) {
  return v.isNull() || (v.is<float>() && isfinite(v.as<float>()) && v.as<float>() >= low && v.as<float>() <= high);
}
inline bool validMessage(JsonDocument &d) {
  if (!d["v"].is<int>() || d["v"].as<int>() != 1 || !nonempty(d["source"])) return false;
  const String type = d["type"] | "";
  if (type == "command" || type == "ack") {
    if (!nonempty(d["command_id"]) || !nonempty(d["rail_id"]) || !d["enabled"].is<bool>()) return false;
  }
  if (type == "command") return nonempty(d["destination"]) && nonempty(d["reason"]) && d["action"] == "SET_RAIL_ENABLED";
  if (type == "ack") {
    String status = d["status"] | "";
    return (status == "APPLIED" || status == "ALREADY_APPLIED" || status == "REJECTED_PROTECTED" ||
      status == "REJECTED_UNARMED" || status == "REJECTED_UNSAFE" || status == "REJECTED_INVALID" || status == "ERROR") && d["controller_uptime_ms"].is<uint32_t>();
  }
  if (type == "bridge_status" || type == "diagnostic") return true;
  if (type != "telemetry" || !d["seq"].is<uint32_t>() || !d["uptime_ms"].is<uint32_t>() ||
      !d["rails"].is<JsonArray>() || !d["fault_flags"].is<JsonArray>() ||
      !bounded(d["ambient_temp_c"], -55, 125) || !bounded(d["bus_voltage_v"], 0, 30)) return false;
  JsonArray rails = d["rails"];
  if (rails.size() < 1 || rails.size() > 16) return false;
  for (size_t i = 0; i < rails.size(); ++i) {
    JsonObject r = rails[i].as<JsonObject>();
    if (r.isNull() || !r.containsKey("v") || !r.containsKey("a") || !r.containsKey("hotspot_c") ||
        !nonempty(r["id"]) || !r["enabled"].is<bool>() || !r["sensor_valid"].is<bool>() ||
        !bounded(r["hotspot_c"], -55, 125) || !bounded(r["a"], 0, 10) || !bounded(r["v"], 0, 30)) return false;
    if (r["sensor_valid"].as<bool>() && (r["hotspot_c"].isNull() || r["a"].isNull() || r["v"].isNull())) return false;
    for (size_t j = 0; j < i; ++j) if (strcmp(r["id"], rails[j]["id"]) == 0) return false;
  }
  return true;
}

// Parse exactly one complete document. ArduinoJson's stream parser otherwise
// permits trailing content, which the laptop's strict JSON decoder rejects.
struct BoundedJsonInput {
  const uint8_t *bytes; size_t length, position=0;
  BoundedJsonInput(const uint8_t *p,size_t n):bytes(p),length(n) {}
  int read() { return position<length?bytes[position++]:-1; }
  size_t readBytes(char *out,size_t wanted) {
    size_t n=length-position<wanted?length-position:wanted;
    memcpy(out,bytes+position,n); position+=n; return n;
  }
};
inline bool parseMessage(JsonDocument &doc,const uint8_t *bytes,size_t length) {
  if (!length || length>MAX_LINE || memchr(bytes,0,length)) return false;
  BoundedJsonInput input(bytes,length);
  if (deserializeJson(doc,input,DeserializationOption::NestingLimit(8))) return false;
  while (input.position<length) {
    char c=bytes[input.position++]; if (c!=' ' && c!='\t' && c!='\r' && c!='\n') return false;
  }
  return validMessage(doc);
}

struct LineReader {
  char data[MAX_LINE];
  size_t length = 0;
  bool dropping = false;
  uint32_t errors = 0;
  template<class Handler> void poll(Stream &serial, Handler handler) {
    // Per-loop budget keeps malformed floods from starving local protection.
    for (size_t budget = 0; serial.available() && budget < MAX_LINE; ++budget) {
      char c = static_cast<char>(serial.read());
      if (c == '\n') {
        if (!dropping && length) {
          data[length] = 0;
          JsonDocument doc;
          if (parseMessage(doc,reinterpret_cast<const uint8_t *>(data),length)) handler(doc, data);
          else ++errors;
        }
        length = 0; dropping = false;
      } else if (!dropping && c != '\r') {
        if (length < MAX_LINE - 1) data[length++] = c;
        else { dropping = true; length = 0; ++errors; }
      }
    }
  }
};

inline void emit(JsonDocument &doc, Stream &out) {
  if (measureJson(doc) + 1 <= MAX_LINE) { serializeJson(doc, out); out.write('\n'); }
}
