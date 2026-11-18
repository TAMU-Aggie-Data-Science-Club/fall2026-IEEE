#include "espnow_packet.h"
#include <assert.h>
#include <iostream>
#include <vector>
#include <string>
#include <stdlib.h>
using namespace gridradio;
std::vector<uint8_t> unhex(const char *text) {
  std::string s(text); std::vector<uint8_t> out;
  if (s.size()%2) exit(2);
  for (size_t i=0;i<s.size();i+=2) out.push_back(strtoul(s.substr(i,2).c_str(),nullptr,16));
  return out;
}
void print(const uint8_t *bytes,size_t n) {
  const char *hex="0123456789abcdef";
  for (size_t i=0;i<n;++i) std::cout<<hex[bytes[i]>>4]<<hex[bytes[i]&15];
  std::cout<<"\n";
}
int main(int argc,char **argv) {
  uint8_t packet[kMaxPacket], out[kMaxMessage]; Header complete; size_t length=0;
  if (argc==7 && std::string(argv[1])=="encode") {
    auto raw=unhex(argv[2]);
    for (uint8_t i=0;i<(raw.size()+kPayload-1)/kPayload;++i) {
      size_t n=fragment(raw.data(),raw.size(),atoi(argv[3]),strtoul(argv[4],nullptr,10),strtoul(argv[5],nullptr,10),strtoul(argv[6],nullptr,10),i,packet);
      if (!n) return 2; print(packet,n);
    }
    return 0;
  }
  if (argc>2 && std::string(argv[1])=="decode") {
    Reassembler receiver;
    for (int i=2;i<argc;++i) {
      auto data=unhex(argv[i]);
      if (receiver.accept(data.data(),data.size(),10,kController,101,out,length,complete)) { print(out,length); return 0; }
    }
    return 3;
  }
  std::vector<uint8_t> raw(kMaxMessage);
  for (size_t i=0;i<raw.size();++i) raw[i]=i*31;
  Reassembler receiver;
  size_t first=fragment(raw.data(),raw.size(),kBridge,201,1,101,0,packet);
  assert(first==220);
  assert(!receiver.accept(packet,first,0,kController,101,out,length,complete));
  assert(!receiver.accept(packet,first,1,kController,101,out,length,complete));
  assert(receiver.duplicates==1);
  for (int i=10;i>=1;--i) {
    size_t n=fragment(raw.data(),raw.size(),kBridge,201,1,101,i,packet);
    bool done=receiver.accept(packet,n,10,kController,101,out,length,complete);
    assert(done==(i==1));
  }
  assert(length==raw.size() && !memcmp(out,raw.data(),length));
  size_t n=fragment(raw.data(),raw.size(),kBridge,201,2,101,0,packet);
  assert(!receiver.accept(packet,n,20,kController,101,out,length,complete));
  receiver.expire(1520); assert(receiver.expired==1);
  packet[2]=2;
  assert(!receiver.accept(packet,n,1521,kController,101,out,length,complete));
  const uint8_t small[]={'a','b','c','\n'};
  n=fragment(small,4,kBridge,201,3,101,0,packet); packet[n-1]^=1;
  assert(!receiver.accept(packet,n,1522,kController,101,out,length,complete));
  n=fragment(small,4,kBridge,201,4,99,0,packet);
  assert(!receiver.accept(packet,n,1523,kController,101,out,length,complete));
  assert(receiver.errors==3);
  std::cout<<"native firmware packet checks passed\n";
  return 0;
}
