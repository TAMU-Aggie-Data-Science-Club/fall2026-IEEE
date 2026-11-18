import importlib.util
from pathlib import Path
import pytest
from grid_algorithm.protocol import encode,decode
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant


def smoke_module():
    spec=importlib.util.spec_from_file_location("grid_smoke",Path("algorithm/firmware/scripts/wireless_smoke.py"))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


@pytest.mark.parametrize("simulated,physical",[(False,False),(True,True),(None,None)])
def test_bench_tool_never_sends_to_real_or_unverified_io(monkeypatch,simulated,physical):
    import serial
    writes=[]; frame=Plant(load_config()).sample()
    frame.update(simulated_sensors=simulated,physical_outputs_enabled=physical)
    class Connection:
        in_waiting=4096
        def __init__(self,*args,**kwargs): self.data=encode(frame)
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def reset_input_buffer(self): pass
        def read(self,n): data=self.data; self.data=b""; return data
        def write(self,data): writes.append(data)
    monkeypatch.setattr(serial,"Serial",Connection)
    with pytest.raises(RuntimeError,match="requires explicit"): smoke_module().run("TEST_ONLY","rail_2",1)
    assert writes==[]


def test_firmware_safe_configuration_and_no_uart_default():
    controller=Path("algorithm/firmware/rig_controller/platformio.ini").read_text()
    bridge=Path("algorithm/firmware/bridge/platformio.ini").read_text()
    assert "-DSIMULATED_SENSORS=1" in controller and "-DPHYSICAL_OUTPUTS=0" in controller
    assert "-DENABLE_ESPNOW=1" in controller and "-DENABLE_ESPNOW=1" in bridge
    assert "controller_esp32dev" in controller and "bridge_esp32dev" in bridge
    assert "HARDWARE_VERIFIED = false" in Path("algorithm/firmware/rig_controller/include/hardware_config.h").read_text()
    assert "lastCommand" not in Path("algorithm/firmware/rig_controller/src/main.cpp").read_text()
    assert "radio.healthy" in Path("algorithm/firmware/rig_controller/src/main.cpp").read_text()
