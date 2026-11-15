#pragma once
#ifndef SIMULATED_IO
#define SIMULATED_IO 1
#endif
constexpr int UART_RX = -1, UART_TX = -1;
#if !SIMULATED_IO
static_assert(UART_RX >= 0 && UART_TX >= 0, "Approve UART pins and common 3.3 V logic ground first");
#endif
