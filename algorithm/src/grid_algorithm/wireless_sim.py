"""Deterministic ESP-NOW envelope path around the existing simulated controller.

MACs here are explicit in-memory test addresses, not physical configuration.
The laptop's real SerialTransport never imports this codec.
"""
from .espnow import Reassembler, fragment, BRIDGE, CONTROLLER
from .protocol import encode, decode
from .transport import FakeBridge

SIM_A = bytes.fromhex("020000000001")
SIM_B = bytes.fromhex("020000000002")


class WirelessBridge(FakeBridge):
    def __init__(self, controller):
        super().__init__(controller)
        self.a_session,self.b_session = 101,201
        self.a_rx = Reassembler(CONTROLLER,self.a_session,SIM_B)
        self.b_rx = Reassembler(BRIDGE,self.b_session,SIM_A)
        self.ids = {CONTROLLER:0,BRIDGE:0}
        self.radio_connected = True
        self.drop_fragments: set[int] = set()
        self.reverse_fragments = False
        self.duplicate_fragments = False
        self.now = 0.

    def transfer(self, raw: bytes, sender: int) -> bytes | None:
        if not self.connected: raise ConnectionError("USB disconnected")
        if not self.radio_connected: return None
        self.ids[sender]+=1
        receiver = self.a_rx if sender==BRIDGE else self.b_rx
        session = self.b_session if sender==BRIDGE else self.a_session
        packets = fragment(raw,sender,session,self.ids[sender],receiver.session)
        indexed = list(enumerate(packets))
        if self.reverse_fragments: indexed.reverse()
        result = None
        for index,packet in indexed:
            if index in self.drop_fragments: continue
            self.now+=.001
            value = receiver.accept(packet,self.now,SIM_B if sender==BRIDGE else SIM_A)
            if value is not None: result=value
            if self.duplicate_fragments: receiver.accept(packet,self.now,SIM_B if sender==BRIDGE else SIM_A)
        return result

    def send(self, command):
        raw = encode(command)
        complete = self.transfer(raw,BRIDGE)
        self.forwarded.append(raw)
        if complete is None: return None
        request = decode(complete)
        if request["type"]!="command": raise ValueError("downstream commands only")
        ack = self.controller.apply(request) # ONLY the controller generates applied ACKs
        upstream = self.transfer(encode(ack),CONTROLLER)
        if self.drop_acks:
            self.drop_acks-=1; return None
        return decode(upstream) if upstream is not None else None

    def telemetry(self):
        self.controller.protect()
        frame = self.controller.plant.sample()
        frame.update(controller_session=self.a_session,simulated_sensors=True,physical_outputs_enabled=False)
        raw = encode(frame)
        upstream = self.transfer(raw,CONTROLLER)
        if upstream is None: raise ConnectionError("ESP-NOW telemetry lost")
        return decode(upstream)

    def reboot_controller(self):
        self.controller.reboot(); self.a_session+=1
        self.a_rx=Reassembler(CONTROLLER,self.a_session,SIM_B)
        # Observe fresh telemetry before host operations can proceed.

    def reboot_bridge(self):
        self.b_session+=1
        self.b_rx=Reassembler(BRIDGE,self.b_session,SIM_A)
