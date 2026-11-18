from grid_algorithm.wireless_sim import WirelessBridge
from grid_algorithm.simulator import Plant,RigController
from grid_algorithm.contracts import load_config
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_model.inference import Predictor


def setup():
    config=load_config(); plant=Plant(config); bridge=WirelessBridge(RigController(plant))
    app=Coordinator(config,Predictor(),Policy(config),bridge)
    return plant,bridge,app


def test_reordered_duplicated_wireless_command_and_controller_ack():
    plant,bridge,app=setup(); bridge.reverse_fragments=True; bridge.duplicate_fragments=True
    app.accept(bridge.telemetry(),0)
    command=app.policy.command("rail_2",False,"test",0)
    app.send(command,0)
    assert not plant.enabled["rail_2"] and app.acks[-1]["status"]=="APPLIED"
    assert app.acks[-1]["source"]=="esp32_rig_01"
    bridge.controller.plant.step(); app.accept(bridge.telemetry(),1)
    assert app.policy.state["rail_2"]=="SHED_CONFIRMED"


def test_partial_command_never_executes_then_retry_same_id_recovers():
    plant,bridge,app=setup(); app.accept(bridge.telemetry(),0)
    command=app.policy.command("rail_2",False,"x"*100,0)
    bridge.drop_fragments={1}; app.send(command,0)
    assert plant.enabled["rail_2"] and app.acks==[]
    bridge.drop_fragments=set(); app.tick(1)
    assert app.commands[0]==app.commands[1] and not plant.enabled["rail_2"]


def test_lost_ack_duplicate_command_and_radio_disconnect():
    plant,bridge,app=setup(); app.accept(bridge.telemetry(),0); bridge.drop_acks=1
    command=app.policy.command("rail_2",False,"test",0); app.send(command,0); app.tick(1)
    assert app.acks[-1]["status"]=="ALREADY_APPLIED" and not plant.enabled["rail_2"]
    bridge.radio_connected=False
    command=app.policy.command("rail_3",False,"test",1); app.send(command,1)
    assert app.policy.state["rail_3"]=="SHED_REQUESTED" and plant.enabled["rail_3"]
    app.tick(10); assert app.policy.state["rail_3"]=="FAULT"
    bridge.radio_connected=True
    assert bridge.telemetry()["source"]=="esp32_rig_01"


def test_controller_and_bridge_reboots_do_not_restore_loads():
    plant,bridge,app=setup(); plant.time=100; app.accept(bridge.telemetry(),100)
    command=app.policy.command("rail_2",False,"test",100); bridge.drop_acks=1; app.send(command,100)
    bridge.reboot_controller()
    assert not app.accept(bridge.telemetry(),101) and not app.armed_session
    assert not any(plant.enabled.values())
    bridge.reboot_bridge()
    plant.step(); app.accept(bridge.telemetry(),102)
    assert not any(plant.enabled.values()) and not app.policy.pending
