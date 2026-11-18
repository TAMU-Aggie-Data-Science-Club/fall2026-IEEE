#pragma once
// Header-only shared implementation: both independent PlatformIO projects compile
// exactly this transport, with no relative external source-filter assumptions.
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <freertos/queue.h>
#include "radio_config.h"
#include "espnow_packet.h"
#include "protocol.h"

class EspNowTransport {
  struct Rx { uint8_t bytes[gridradio::kMaxPacket]; uint16_t length; };
  struct Tx { uint8_t bytes[MAX_LINE]; uint16_t length; uint32_t id, target; } tx[4];
  QueueHandle_t rxQueue=nullptr, completionQueue=nullptr;
  gridradio::Reassembler assembly;
  uint8_t peer[6]={}, role, head=0, count=0, fragmentIndex=0;
  uint32_t session, peerSession=0, nextId=0, nextInit=0, lastRx=0, sentAt=0;
  uint32_t lastPeerMessage=0;
  uint32_t retiredSessions[4]={}; uint8_t retiredIndex=0;
  bool initialized=false, configured=false, heard=false, busy=false;
  uint8_t complete[MAX_LINE+1], packet[gridradio::kMaxPacket];
  uint32_t messagesSent=0, messagesReceived=0, sendFailures=0, parseErrors=0, txDrops=0, callbackTimeouts=0, peerResets=0;
  volatile uint32_t rxDrops=0, invalidPeer=0;
  const char *initError="not_started";
  static EspNowTransport *&instance() { static EspNowTransport *value=nullptr; return value; }
  static void onReceive(const uint8_t *mac,const uint8_t *data,int length) {
    auto *self=instance(); if (!self) return;
    if (!self->configured || memcmp(mac,self->peer,6)) { ++self->invalidPeer; return; }
    if (length<int(gridradio::kHeader) || length>int(gridradio::kMaxPacket)) { ++self->rxDrops; return; }
    Rx item; item.length=length; memcpy(item.bytes,data,length);
    if (xQueueSend(self->rxQueue,&item,0)!=pdTRUE) ++self->rxDrops;
  }
  static void onSent(const uint8_t *,esp_now_send_status_t status) {
    auto *self=instance(); if (!self) return;
    uint8_t result=status==ESP_NOW_SEND_SUCCESS?1:0;
    xQueueSend(self->completionQueue,&result,0);
  }
  static int hex(char c) {
    if (c>='0' && c<='9') return c-'0';
    if (c>='a' && c<='f') return c-'a'+10;
    if (c>='A' && c<='F') return c-'A'+10;
    return -1;
  }
  static bool key(const char *text,uint8_t *bytes) {
    if (strlen(text)!=32) return false;
    bool nonzero=false;
    for (int i=0;i<16;++i) { int a=hex(text[2*i]), b=hex(text[2*i+1]); if (a<0 || b<0) return false; bytes[i]=a*16+b; nonzero|=bytes[i]!=0; }
    return nonzero;
  }
  bool peerAddress() {
    const char *text=ESPNOW_PEER_MAC;
    if (strlen(text)!=17) return false;
    bool nonzero=false;
    for (int i=0;i<6;++i) {
      int a=hex(text[3*i]), b=hex(text[3*i+1]);
      if (a<0 || b<0 || (i<5 && text[3*i+2]!=':')) return false;
      peer[i]=a*16+b; nonzero|=peer[i]!=0;
    }
    return nonzero && !(peer[0]&1); // no zero, multicast or broadcast peers
  }
  bool validDirection(JsonDocument &doc,const gridradio::Header &header) {
    const String type=doc["type"]|"";
    if (role==gridradio::kBridge) return doc["source"]=="esp32_rig_01" && (type=="telemetry" || type=="ack" || type=="diagnostic");
    if (type=="diagnostic") return doc["source"]=="esp32_bridge_01" && doc["event"]=="heartbeat";
    return type=="command" && header.targetSession==session && doc["destination"]=="esp32_rig_01" &&
           (doc["source"]=="laptop" || doc["source"]=="esp32_bridge_01");
  }
  void finishPacket(bool success) {
    busy=false;
    if (!count) return;
    if (!success) { ++sendFailures; head=(head+1)%4; --count; fragmentIndex=0; return; }
    ++fragmentIndex;
    if (fragmentIndex>=(tx[head].length+gridradio::kPayload-1)/gridradio::kPayload) {
      ++messagesSent; head=(head+1)%4; --count; fragmentIndex=0;
    }
  }
 public:
  explicit EspNowTransport(uint8_t localRole):role(localRole),session(esp_random()) { if (!session) session=1; }
  const char *identity() const { return role==gridradio::kBridge?"esp32_bridge_01":"esp32_rig_01"; }
  uint32_t bootSession() const { return session; }
  bool healthy(uint32_t now) const { return initialized && heard && uint32_t(now-lastRx)<5000; }
  bool begin() {
    instance()=this; nextInit=millis()+5000;
    if (!rxQueue) rxQueue=xQueueCreate(16,sizeof(Rx));
    if (!completionQueue) completionQueue=xQueueCreate(4,sizeof(uint8_t));
    if (!rxQueue || !completionQueue) { initError="queue_allocation_failed"; return false; }
    if (!ENABLE_ESPNOW) { initError="radio_disabled"; return false; }
    WiFi.mode(WIFI_STA); WiFi.disconnect(false,false); WiFi.setSleep(false);
    if (esp_wifi_set_channel(ESPNOW_CHANNEL,WIFI_SECOND_CHAN_NONE)!=ESP_OK) { initError="channel_setup_failed"; return false; }
    esp_now_deinit(); initialized=false;
    if (esp_now_init()!=ESP_OK) { initError="espnow_init_failed"; return false; }
    if (esp_now_register_recv_cb(onReceive)!=ESP_OK || esp_now_register_send_cb(onSent)!=ESP_OK) { initError="callback_registration_failed"; esp_now_deinit(); return false; }
    configured=peerAddress();
    if (configured) {
      esp_now_peer_info_t info={}; memcpy(info.peer_addr,peer,6);
      info.channel=ESPNOW_CHANNEL; info.ifidx=WIFI_IF_STA; info.encrypt=bool(ESPNOW_ENCRYPTION);
      if (ESPNOW_ENCRYPTION) {
        uint8_t pmk[16];
        if (!key(ESPNOW_PMK_HEX,pmk) || !key(ESPNOW_LMK_HEX,info.lmk) || esp_now_set_pmk(pmk)!=ESP_OK) { initError="invalid_encryption_configuration"; configured=false; esp_now_deinit(); return false; }
      }
      if (esp_now_add_peer(&info)!=ESP_OK) { initError="peer_registration_failed"; esp_now_deinit(); return false; }
    }
    initialized=true; initError=configured?"none":"peer_missing_or_invalid"; return true;
  }
  bool sendRaw(const uint8_t *bytes,size_t length) {
    if (!initialized || !configured || !length || length>MAX_LINE || bytes[length-1]!='\n' || count==4) { ++txDrops; return false; }
    JsonDocument doc;
    if (!parseMessage(doc,bytes,length)) { ++parseErrors; return false; }
    if (doc["type"]=="command" && !peerSession) { ++txDrops; return false; }
    Tx &item=tx[(head+count)%4]; memcpy(item.bytes,bytes,length); item.length=length;
    item.id=++nextId; if (!item.id) item.id=++nextId; item.target=peerSession; ++count;
    return true;
  }
  bool send(JsonDocument &doc) {
    uint8_t bytes[MAX_LINE]; size_t n=measureJson(doc);
    if (n+1>MAX_LINE || !validMessage(doc)) { ++parseErrors; return false; }
    serializeJson(doc,bytes,n+1); bytes[n]='\n'; return sendRaw(bytes,n+1);
  }
  void heartbeat() {
    JsonDocument doc; doc["v"]=1; doc["type"]="diagnostic"; doc["source"]=identity();
    doc["event"]="heartbeat"; doc["uptime_ms"]=millis(); doc["boot_session"]=session;
    send(doc);
  }
  template<class Handler> void poll(Handler handle) {
    const uint32_t now=millis();
    if (!initialized && ENABLE_ESPNOW && int32_t(now-nextInit)>=0) begin();
    assembly.expire(now);
    Rx item;
    for (int budget=0; budget<8 && rxQueue && xQueueReceive(rxQueue,&item,0)==pdTRUE; ++budget) {
      size_t n=0; gridradio::Header header;
      if (!assembly.accept(item.bytes,item.length,now,role,session,complete,n,header)) continue;
      bool retired=false; for (uint32_t old:retiredSessions) if (old && old==header.session) retired=true;
      if (retired || !n || complete[n-1]!='\n' || memchr(complete,0,n) || memchr(complete,'\n',n-1)) { ++parseErrors; continue; }
      JsonDocument doc;
      if (!parseMessage(doc,complete,n) || !validDirection(doc,header)) { ++parseErrors; continue; }
      if (peerSession==header.session && lastPeerMessage) {
        uint32_t delta=header.message-lastPeerMessage;
        // Delayed complete commands/heartbeats must not supersede a newer peer
        // operation or refresh the link. Fragment order WITHIN a message is free.
        if (!delta || delta>0x80000000u) { ++parseErrors; continue; }
      }
      if (peerSession && peerSession!=header.session) {
        retiredSessions[retiredIndex]=peerSession; retiredIndex=(retiredIndex+1)%4;
        ++peerResets;
        // Discard queued work addressed to the old peer boot. Never replay it after reboot.
        if (!busy) { count=0; fragmentIndex=0; }
      }
      peerSession=header.session; lastPeerMessage=header.message; heard=true; lastRx=now; ++messagesReceived;
      complete[n]=0; handle(doc,reinterpret_cast<const char *>(complete),n);
    }
    uint8_t result;
    while (completionQueue && xQueueReceive(completionQueue,&result,0)==pdTRUE) if (busy) finishPacket(result==1);
    if (busy && uint32_t(now-sentAt)>250) {
      ++callbackTimeouts; ++sendFailures; busy=false; count=0; fragmentIndex=0;
      initialized=false; heard=false; peerSession=0; esp_now_deinit(); nextInit=now+5000;
    }
    if (!initialized || !configured || busy || !count) return;
    Tx &current=tx[head];
    if (current.target && current.target!=peerSession) { finishPacket(false); return; }
    size_t n=gridradio::fragment(current.bytes,current.length,role,session,current.id,current.target,fragmentIndex,packet);
    if (!n) { finishPacket(false); return; }
    busy=true; sentAt=now;
    if (esp_now_send(peer,packet,n)!=ESP_OK) finishPacket(false);
  }
  void status(Stream &out,uint32_t serialErrors=0) const {
    JsonDocument doc; doc["v"]=1; doc["type"]=role==gridradio::kBridge?"bridge_status":"diagnostic";
    doc["source"]=identity(); doc["transport"]="espnow"; doc["event"]="link_status";
    doc["local_mac"]=WiFi.macAddress(); doc["channel"]=ESPNOW_CHANNEL;
    doc["link_initialized"]=initialized; doc["peer_configured"]=configured;
    doc["initialization_error"]=initError;
    doc["peer_recent"]=healthy(millis()); doc["encrypted"]=bool(ESPNOW_ENCRYPTION);
    doc["boot_session"]=session; doc["peer_session"]=peerSession;
    if (heard) doc["last_rx_age_ms"]=uint32_t(millis()-lastRx); else doc["last_rx_age_ms"]=nullptr;
    doc["messages_sent"]=messagesSent; doc["messages_received"]=messagesReceived;
    doc["failed_transmissions"]=sendFailures; doc["fragment_errors"]=assembly.errors;
    doc["reassembly_timeouts"]=assembly.expired; doc["duplicate_fragments"]=assembly.duplicates;
    doc["queue_drops"]=uint32_t(rxDrops)+txDrops+assembly.capacityDrops;
    doc["invalid_peer_packets"]=uint32_t(invalidPeer); doc["parse_errors"]=parseErrors+serialErrors;
    doc["callback_timeouts"]=callbackTimeouts; doc["peer_resets"]=peerResets;
    emit(doc,out);
  }
};
