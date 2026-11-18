#pragma once
// Portable wire codec. No Arduino, heap allocations, packed structs or host-endian fields.
#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace gridradio {
constexpr size_t kHeader = 28, kPayload = 192, kMaxMessage = 2048;
constexpr size_t kMaxPacket = kHeader + kPayload;
constexpr uint8_t kVersion = 1, kController = 1, kBridge = 2;
constexpr uint32_t kExpiryMs = 1500, kDuplicateMs = 10000;
static_assert(kMaxPacket <= 250, "ESP-NOW v1 packet limit");
inline void put16(uint8_t *p, uint16_t n) { p[0]=n; p[1]=n>>8; }
inline void put32(uint8_t *p, uint32_t n) { for (int i=0;i<4;++i) p[i]=n>>(8*i); }
inline uint16_t get16(const uint8_t *p) { return uint16_t(p[0]) | uint16_t(p[1])<<8; }
inline uint32_t get32(const uint8_t *p) { return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24; }
inline uint32_t crc32(const uint8_t *data, size_t length) {
  uint32_t crc=0xffffffffu;
  for (size_t i=0;i<length;++i) { crc^=data[i]; for (int b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xedb88320u:0u); }
  return ~crc;
}
struct Header {
  uint8_t sender=0, receiver=0, index=0, count=0;
  uint32_t session=0, message=0, crc=0, targetSession=0;
  uint16_t total=0, length=0;
};
inline bool parse(const uint8_t *data, size_t length, Header &h) {
  if (length<kHeader || length>kMaxPacket || data[0]!='E' || data[1]!='G' || data[2]!=kVersion || data[5]!=0) return false;
  h.sender=data[3]; h.receiver=data[4]; h.session=get32(data+6); h.message=get32(data+10);
  h.total=get16(data+14); h.index=data[16]; h.count=data[17]; h.length=get16(data+18);
  h.crc=get32(data+20); h.targetSession=get32(data+24);
  if (!h.session || !h.message || !h.total || h.total>kMaxMessage ||
      h.sender+h.receiver!=3 || h.sender==h.receiver || h.sender<1 || h.sender>2 ||
      h.count!=(h.total+kPayload-1)/kPayload || h.index>=h.count || length!=kHeader+h.length) return false;
  const size_t offset=h.index*kPayload;
  const size_t expected=h.total-offset<kPayload?h.total-offset:kPayload;
  return h.length==expected;
}
inline size_t fragment(const uint8_t *data, size_t length, uint8_t sender, uint32_t session,
                       uint32_t message, uint32_t targetSession, uint8_t index, uint8_t *out) {
  if (!length || length>kMaxMessage || !session || !message || sender<1 || sender>2 || index>=(length+kPayload-1)/kPayload) return 0;
  const size_t offset=index*kPayload, n=length-offset<kPayload?length-offset:kPayload;
  out[0]='E'; out[1]='G'; out[2]=kVersion; out[3]=sender; out[4]=3-sender; out[5]=0;
  put32(out+6,session); put32(out+10,message); put16(out+14,length);
  out[16]=index; out[17]=(length+kPayload-1)/kPayload; put16(out+18,n);
  put32(out+20,crc32(data,length)); put32(out+24,targetSession);
  memcpy(out+kHeader,data+offset,n); return kHeader+n;
}

class Reassembler {
  struct Slot { bool used=false; Header h; uint16_t mask=0; uint32_t started=0; uint8_t bytes[kMaxMessage]; } slots[2];
  struct Seen { bool used=false; uint32_t session=0, message=0, at=0; } seen[8];
  size_t nextSeen=0;
 public:
  uint32_t errors=0, expired=0, duplicates=0, capacityDrops=0;
  void expire(uint32_t now) { for (auto &s:slots) if (s.used && uint32_t(now-s.started)>=kExpiryMs) { s.used=false; ++expired; } }
  // Return a complete exact message only after all fragments and CRC agree.
  bool accept(const uint8_t *packet, size_t length, uint32_t now, uint8_t localRole,
              uint32_t localSession, uint8_t *out, size_t &outLength, Header &complete) {
    expire(now); outLength=0; Header h;
    if (!parse(packet,length,h) || h.receiver!=localRole || (h.targetSession && h.targetSession!=localSession)) { ++errors; return false; }
    for (const auto &s:seen) if (s.used && s.session==h.session && s.message==h.message && uint32_t(now-s.at)<kDuplicateMs) { ++duplicates; return false; }
    Slot *slot=nullptr;
    for (auto &s:slots) if (s.used && s.h.session==h.session && s.h.message==h.message) { slot=&s; break; }
    if (!slot) {
      for (auto &s:slots) if (!s.used) { slot=&s; break; }
      if (!slot) { ++capacityDrops; return false; }
      slot->used=true; slot->h=h; slot->mask=0; slot->started=now;
    }
    if (slot->h.total!=h.total || slot->h.count!=h.count || slot->h.crc!=h.crc || slot->h.targetSession!=h.targetSession || slot->h.sender!=h.sender) {
      slot->used=false; ++errors; return false;
    }
    const uint16_t bit=uint16_t(1)<<h.index;
    uint8_t *destination=slot->bytes+h.index*kPayload;
    if (slot->mask&bit) {
      if (memcmp(destination,packet+kHeader,h.length)) { slot->used=false; ++errors; }
      else ++duplicates;
      return false;
    }
    memcpy(destination,packet+kHeader,h.length); slot->mask|=bit;
    if (slot->mask!=((uint16_t(1)<<h.count)-1)) return false;
    slot->used=false;
    if (crc32(slot->bytes,h.total)!=h.crc) { ++errors; return false; }
    memcpy(out,slot->bytes,h.total); outLength=h.total; complete=h;
    seen[nextSeen].used=true; seen[nextSeen].session=h.session; seen[nextSeen].message=h.message; seen[nextSeen].at=now;
    nextSeen=(nextSeen+1)%8;
    return true;
  }
};
} // namespace gridradio
