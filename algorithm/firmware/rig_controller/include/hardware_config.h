#pragma once
// No physical pin assignments have been approved. Keep -1 until commissioned.
#include "../../common/radio_config.h"
#ifndef SIMULATED_SENSORS
#define SIMULATED_SENSORS 1
#endif
#ifndef PHYSICAL_OUTPUTS
#define PHYSICAL_OUTPUTS 0
#endif
constexpr int ONEWIRE_PIN = -1;
constexpr int RELAY_PINS[3] = {-1, -1, -1};
constexpr int CURRENT_PINS[3] = {-1, -1, -1};
constexpr int VOLTAGE_PINS[3] = {-1, -1, -1};
constexpr int BUS_PIN = -1, ARM_PIN = -1;
constexpr bool ACTIVE_HIGH = true;
constexpr bool HARDWARE_VERIFIED = false;
constexpr bool LIMITS_VERIFIED = false, RELAY_POLARITY_VERIFIED = false;
constexpr float WARNING_C[3] = {70, 70, 70};
constexpr float CRITICAL_C[3] = {80, 80, 80};
constexpr bool SHED_ALLOWED[3] = {false, true, true};
// ADC scale/offset must be measured with the actual sensor chain.
constexpr float CURRENT_ZERO_V[3] = {1.65, 1.65, 1.65};
constexpr float CURRENT_V_PER_A[3] = {.185, .185, .185};
constexpr float DIVIDER_RATIO = 0; // deliberately invalid until calibrated
constexpr uint32_t MIN_OFF_MS = 60000, LINK_TIMEOUT_MS = 5000;
#if PHYSICAL_OUTPUTS
static_assert(!SIMULATED_SENSORS && ENABLE_ESPNOW && ESPNOW_ENCRYPTION, "Physical output requires real sensors and encrypted peer communication");
static_assert(HARDWARE_VERIFIED && LIMITS_VERIFIED && RELAY_POLARITY_VERIFIED && ONEWIRE_PIN >= 0 && ARM_PIN >= 0 && BUS_PIN >= 0 && DIVIDER_RATIO > 0,
              "Commission hardware configuration before enabling physical outputs");
static_assert(RELAY_PINS[0] >= 0 && RELAY_PINS[1] >= 0 && RELAY_PINS[2] >= 0 &&
              CURRENT_PINS[0] >= 0 && CURRENT_PINS[1] >= 0 && CURRENT_PINS[2] >= 0 &&
              VOLTAGE_PINS[0] >= 0 && VOLTAGE_PINS[1] >= 0 && VOLTAGE_PINS[2] >= 0,
              "All actuator and ADC pins require approval");
#endif
#if !SIMULATED_SENSORS
static_assert(ONEWIRE_PIN>=0 && BUS_PIN>=0 && DIVIDER_RATIO>0 &&
              CURRENT_PINS[0]>=0 && CURRENT_PINS[1]>=0 && CURRENT_PINS[2]>=0 &&
              VOLTAGE_PINS[0]>=0 && VOLTAGE_PINS[1]>=0 && VOLTAGE_PINS[2]>=0,
              "Real sensor mappings and measured calibration must be configured");
#endif
