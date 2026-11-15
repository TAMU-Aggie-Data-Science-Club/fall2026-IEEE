from .protocol import encode, decode, Framer


class FakeBridge:
    """Byte-for-byte routing through the same validator as the serial driver."""
    def __init__(self, controller):
        self.controller = controller
        self.connected = True
        self.drop_acks = 0
        self.forwarded = []

    def send(self, cmd):
        if not self.connected: raise ConnectionError("USB disconnected")
        raw = encode(cmd)
        message = decode(raw)
        if message["type"] != "command": raise ValueError("downstream commands only")
        self.forwarded.append(raw)
        ack = decode(encode(self.controller.apply(message)))
        if self.drop_acks:
            self.drop_acks -= 1
            return None
        return ack

    def telemetry(self):
        if not self.connected: raise ConnectionError("USB disconnected")
        self.controller.protect()
        return decode(encode(self.controller.plant.sample()))


class SerialTransport:
    def __init__(self, port, baud=115200, monitor_only=True):
        self.port, self.baud, self.monitor_only = port, baud, monitor_only
        self.serial = None
        self.framer = Framer()
        self.next_connect = 0.
        self.backoff = 1.

    def connect(self, now):
        import serial
        if now < self.next_connect: return False
        try:
            self.serial = serial.Serial(self.port, self.baud, timeout=0, write_timeout=.2)
            self.backoff = 1.; return True
        except (serial.SerialException, OSError):
            self.next_connect = now + self.backoff
            self.backoff = min(30., self.backoff * 2)
            return False

    def close(self):
        if self.serial: self.serial.close()
        self.serial = None
        self.framer = Framer()

    def receive(self, now):
        if self.serial is None and not self.connect(now): return []
        try: return self.framer.feed(self.serial.read(min(4096, self.serial.in_waiting)))
        except OSError:
            self.close(); self.next_connect = now + self.backoff
            return []

    def send(self, cmd):
        if self.monitor_only: raise PermissionError("physical actuation has not been commissioned")
        if self.serial is None: raise ConnectionError("serial disconnected")
        self.serial.write(encode(cmd))
        return None
