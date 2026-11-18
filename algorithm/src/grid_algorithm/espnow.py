"""Host reference for firmware/common/espnow_packet.h. Not used by USB live mode.

Layout is documented in firmware/README.md; native golden-byte tests ensure parity.
Only the fake wireless integration uses fragmentation on the laptop.
"""
from dataclasses import dataclass
import struct
import zlib
from .protocol import MAX_LINE

HEADER = struct.Struct("<2sBBBBIIHBBHII")
PAYLOAD = 192
EXPIRY_S = 1.5
DUPLICATE_S = 10.
CONTROLLER, BRIDGE = 1, 2


def fragment(raw: bytes, sender: int, session: int, message: int, target_session: int = 0) -> list[bytes]:
    if not 1 <= len(raw) <= MAX_LINE or sender not in (1,2) or not 0 < session < 2**32 or not 0 < message < 2**32 or not 0 <= target_session < 2**32:
        raise ValueError("invalid message/envelope bounds")
    count = (len(raw)+PAYLOAD-1)//PAYLOAD
    crc = zlib.crc32(raw)
    return [HEADER.pack(b"EG",1,sender,3-sender,0,session,message,len(raw),i,count,len(raw[i*PAYLOAD:(i+1)*PAYLOAD]),crc,target_session)
            + raw[i*PAYLOAD:(i+1)*PAYLOAD] for i in range(count)]


@dataclass(frozen=True)
class Envelope:
    sender: int
    receiver: int
    session: int
    message: int
    total: int
    index: int
    count: int
    length: int
    crc: int
    target_session: int


def parse(packet: bytes) -> tuple[Envelope, bytes]:
    if not HEADER.size <= len(packet) <= HEADER.size+PAYLOAD: raise ValueError("invalid packet length")
    magic,version,sender,receiver,flags,session,message,total,index,count,length,crc,target = HEADER.unpack_from(packet)
    if (magic!=b"EG" or version!=1 or flags!=0 or sender not in (1,2) or receiver!=3-sender or
        not session or not message or not 1<=total<=MAX_LINE or count!=(total+PAYLOAD-1)//PAYLOAD or
        index>=count or length!=min(PAYLOAD,total-index*PAYLOAD) or len(packet)!=HEADER.size+length):
        raise ValueError("invalid envelope")
    return Envelope(sender,receiver,session,message,total,index,count,length,crc,target),packet[HEADER.size:]


class Reassembler:
    """Two slots, eight completed IDs, fixed deadlines; expected MAC is mandatory."""
    def __init__(self, role: int, session: int, peer_mac: bytes):
        if role not in (1,2) or not 0 < session < 2**32 or len(peer_mac)!=6 or peer_mac[0]&1 or not any(peer_mac):
            raise ValueError("invalid local role/session/unicast peer")
        self.role,self.session,self.peer_mac = role,session,peer_mac
        self.slots: dict = {}
        self.seen: dict = {}
        self.errors = self.expired = self.duplicates = self.capacity_drops = 0
        self.last_envelope: Envelope | None = None

    def expire(self, now: float) -> None:
        for key,slot in list(self.slots.items()):
            if now-slot[0] >= EXPIRY_S:
                del self.slots[key]; self.expired+=1

    def accept(self, packet: bytes, now: float, sender_mac: bytes) -> bytes | None:
        self.expire(now)
        if sender_mac != self.peer_mac: self.errors+=1; return None
        try: h,part = parse(packet)
        except ValueError: self.errors+=1; return None
        if h.receiver != self.role or h.target_session not in (0,self.session): self.errors+=1; return None
        key = h.session,h.message
        if key in self.seen and now-self.seen[key]<DUPLICATE_S: self.duplicates+=1; return None
        if key not in self.slots:
            if len(self.slots)==2: self.capacity_drops+=1; return None
            self.slots[key] = [now,h,{}]
        _,prior,parts = self.slots[key]
        if (prior.total,prior.count,prior.crc,prior.target_session,prior.sender)!=(h.total,h.count,h.crc,h.target_session,h.sender):
            del self.slots[key]; self.errors+=1; return None
        if h.index in parts:
            if parts[h.index]!=part: del self.slots[key]; self.errors+=1
            else: self.duplicates+=1
            return None
        parts[h.index] = part
        if len(parts)!=h.count: return None
        raw = b"".join(parts[i] for i in range(h.count)); del self.slots[key]
        if zlib.crc32(raw)!=h.crc: self.errors+=1; return None
        if key in self.seen: del self.seen[key]
        self.seen[key]=now
        if len(self.seen)>8: del self.seen[next(iter(self.seen))]
        self.last_envelope=h
        return raw
