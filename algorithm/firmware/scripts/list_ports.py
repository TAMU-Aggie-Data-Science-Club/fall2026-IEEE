"""Display actual ports without opening or changing any attached device."""
from serial.tools.list_ports import comports

ports=list(comports())
for port in ports:
    print(f"{port.device}: {port.description} | {port.hwid} | serial={port.serial_number or 'unknown'}")
if not ports: print("No serial ports found. Check Device Manager, data-capable USB cable and the board-specific USB driver.")
