#pragma once
// A local header is discovered through each project's include/ directory.
#if __has_include("peer_config.h")
#include "peer_config.h"
#endif
#ifndef ENABLE_ESPNOW
#define ENABLE_ESPNOW 1
#endif
#ifndef ESPNOW_CHANNEL
#define ESPNOW_CHANNEL 1
#endif
#ifndef ESPNOW_PEER_MAC
#define ESPNOW_PEER_MAC ""
#endif
#ifndef ESPNOW_ENCRYPTION
#define ESPNOW_ENCRYPTION 0
#endif
#ifndef ESPNOW_PMK_HEX
#define ESPNOW_PMK_HEX ""
#endif
#ifndef ESPNOW_LMK_HEX
#define ESPNOW_LMK_HEX ""
#endif
static_assert(ESPNOW_CHANNEL>=1 && ESPNOW_CHANNEL<=11, "Use an approved common 2.4GHz channel 1..11");
