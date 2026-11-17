import pytest
from grid_model.transformer_predictor import TransformerPredictor
from grid_model.contracts import PredictResponse
from grid_algorithm.contracts import load_config
from grid_algorithm.policy import Policy
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge, SerialTransport
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.protocol import encode
from grid_model.inference import Predictor


def test_wrong_domain_cannot_actuate_even_measured_overtemperature():
    config = load_config(); plant = Plant(config); bridge = FakeBridge(RigController(plant))
    policy = Policy(config); app = Coordinator(config,TransformerPredictor(),policy,bridge)
    app.accept(bridge.telemetry(),0); plant.step(); app.accept(bridge.telemetry(),1)
    assert not app.commands
    app.send(policy.command("rail_2",False,"wrong-domain",1),1)
    assert plant.enabled["rail_2"] and not bridge.forwarded
    forecast = PredictResponse("rail_2",90,100,110,None,"ieee_c57_91","2011","good",hardware_domain="oil_transformer",actuation_eligible=False)
    rail = dict(id="rail_2",enabled=True,sensor_valid=True,hotspot_c=90)
    assert Policy(config,persistence=1).decide(rail,forecast,0) is None


@pytest.mark.parametrize("status",["REJECTED_PROTECTED","REJECTED_UNARMED","REJECTED_UNSAFE","REJECTED_INVALID","ERROR"])
def test_unsuccessful_ack_never_confirms_or_restores(status):
    policy = Policy(load_config()); command=policy.command("rail_2",False,"test",0)
    assert policy.ack(dict(v=1,type="ack",source="esp32_rig_01",command_id=command["command_id"],rail_id="rail_2",status=status,enabled=True))
    assert policy.state["rail_2"] == "FAULT" and policy.retries(100) == []


def test_serial_driver_uses_same_contract_as_two_device_simulator(monkeypatch):
    import serial
    config=load_config(); plant=Plant(config); bridge=FakeBridge(RigController(plant))
    class USB:
        def __init__(self,*args,**kwargs): self.buffer=bytearray(encode(bridge.telemetry())); self.writes=[]
        @property
        def in_waiting(self): return len(self.buffer)
        def read(self,n):
            n=min(n,53); chunk=bytes(self.buffer[:n]); del self.buffer[:n]; return chunk
        def write(self,raw):
            from grid_algorithm.protocol import decode
            self.writes.append(raw); ack=bridge.send(decode(raw)); self.buffer.extend(encode(ack)); return len(raw)
        def close(self): pass
    monkeypatch.setattr(serial,"Serial",USB)
    transport=SerialTransport("TEST_ONLY",monitor_only=False)
    received=[]
    for _ in range(30): received.extend(transport.receive(0))
    assert received[0]["type"] == "telemetry" and len(received[0]["rails"]) == 3
    command=Policy(config).command("rail_2",False,"contract-test",0)
    transport.send(command)
    for _ in range(10): received.extend(transport.receive(1))
    assert received[-1]["type"] == "ack" and received[-1]["command_id"] == command["command_id"]
    assert received[-1]["status"] == "APPLIED" and not plant.enabled["rail_2"]
    assert transport.serial.writes == bridge.forwarded
    transport.close()


def test_independent_rail_profiles_and_cooling_constants():
    config=load_config(); plant=Plant(config)
    assert plant.temps["rail_2"] != plant.temps["rail_3"]
    for _ in range(170): plant.step()
    assert plant.current("rail_2") != plant.current("rail_3")
    assert plant.temps["rail_2"] != plant.temps["rail_3"]
    controller=RigController(plant); policy=Policy(config)
    before=dict(plant.temps)
    for rail in ("rail_2","rail_3"): controller.apply(policy.command(rail,False,"test",plant.time))
    plant.step(60)
    cooling=[(plant.temps[r]-plant.ambient)/(before[r]-plant.ambient) for r in ("rail_2","rail_3")]
    assert cooling[0] != pytest.approx(cooling[1])
