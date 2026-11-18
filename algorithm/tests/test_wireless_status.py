from grid_algorithm.contracts import load_config
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.policy import Policy
from grid_algorithm.simulator import Plant,RigController
from grid_algorithm.wireless_sim import WirelessBridge
from grid_algorithm.transport import SerialTransport
from grid_algorithm.persistence import EventLog
from grid_algorithm.dashboard_state import latest_snapshot,read_events
from grid_model.inference import Predictor


def test_controller_boot_token_clears_pending_even_without_uptime_decrease():
    config=load_config(); bridge=WirelessBridge(RigController(Plant(config)))
    app=Coordinator(config,Predictor(),Policy(config),bridge)
    first=bridge.telemetry(); app.accept(first,0)
    app.policy.command("rail_2",False,"pending",0)
    frame=dict(first,seq=first["seq"]+1,controller_session=999)
    assert not app.accept(frame,1)
    assert not app.armed_session and not app.policy.pending


def test_status_snapshot_keeps_radio_and_serial_distinct_from_ack(tmp_path):
    log=EventLog(tmp_path/"radio.sqlite")
    log.write("run_metadata",dict(mode="live",monitor_only=True),0)
    log.write("serial_status",dict(connected=True,port="TEST_ONLY"),0)
    log.write("bridge_status",dict(v=1,type="bridge_status",source="esp32_bridge_01",event="link_status",peer_recent=False),1)
    log.write("bridge_status",dict(event="command_queued",controller_applied=False,queued=True),2)
    snapshot=latest_snapshot(read_events(tmp_path/"radio.sqlite"))
    assert snapshot["run_metadata"]["mode"]=="live"
    assert snapshot["serial_status"]["connected"]
    assert not snapshot["bridge_status"]["peer_recent"]
    assert snapshot["telemetry"] is None
    log.close()


def test_bridge_heartbeat_cannot_refresh_controller_telemetry_age():
    events=[dict(kind="raw_inbound",utc="2026-11-17T00:00:00+00:00",payload=dict(source="esp32_rig_01",rails=[])),
            dict(kind="bridge_status",utc="2026-11-17T00:01:00+00:00",payload=dict(event="link_status",peer_recent=False))]
    snapshot=latest_snapshot(events)
    assert snapshot["telemetry_utc"]==events[0]["utc"]


def test_serial_disconnect_and_reconnect_status(monkeypatch):
    import serial
    attempts=[]
    class Serial:
        in_waiting=0
        def read(self,n): return b""
        def close(self): pass
    def connect(*args,**kwargs):
        attempts.append(args)
        if len(attempts)==1: raise serial.SerialException("injected unplug")
        return Serial()
    monkeypatch.setattr(serial,"Serial",connect)
    transport=SerialTransport("TEST_ONLY")
    assert transport.receive(0)==[] and not transport.status()["connected"]
    transport.receive(.5); assert len(attempts)==1
    transport.receive(1); assert transport.status()["connected"] and transport.status()["error"] is None
    assert transport.monitor_only
    transport.close()
