"""Explicit bench-only OFF request. Refuses real/unknown sensors or physical outputs.

This is separate from the monitor-only application, not a live actuation override.
Only use known dry-run images with all relay/load connections disconnected.
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"algorithm/src"))
from grid_algorithm.protocol import Framer,encode


def run(port,rail=None,timeout=10.):
    import serial
    command=None; ack=None; parser=Framer(); start=time.monotonic(); sent=0.; attempts=0
    with serial.Serial(port,115200,timeout=.05,write_timeout=.5) as connection:
        connection.reset_input_buffer()
        while time.monotonic()-start<timeout:
            for frame in parser.feed(connection.read(min(4096,max(1,connection.in_waiting)))):
                if frame["type"]=="bridge_status": print(json.dumps(frame))
                if frame["type"]=="ack" and command and frame["command_id"]==command["command_id"]:
                    if (frame["source"]!="esp32_rig_01" or frame["rail_id"]!=rail or frame.get("physical_actuation") is not False or
                        frame["status"] not in {"APPLIED","ALREADY_APPLIED"} or frame["enabled"]):
                        raise RuntimeError("controller did not confirm a simulated OFF action")
                    ack=frame
                if frame["type"]!="telemetry" or frame["source"]!="esp32_rig_01": continue
                if frame.get("simulated_sensors") is not True or frame.get("physical_outputs_enabled") is not False:
                    raise RuntimeError("bench test requires explicit simulated sensors AND disabled physical outputs; no command sent")
                if rail is None: return {"synthetic_telemetry_received":True,"physical_verification":False}
                if command is None:
                    command=dict(v=1,type="command",source="laptop",destination="esp32_rig_01",command_id="BENCH-"+uuid.uuid4().hex[:16],
                                 action="SET_RAIL_ENABLED",rail_id=rail,enabled=False,reason="SIMULATED_ESPNOW_BENCH_TEST")
                if ack and any(r["id"]==rail and r["enabled"] is False for r in frame["rails"]):
                    return {"ack":ack,"subsequent_simulated_state_confirmed":True,"physical_verification":False}
            if command and not ack and attempts<3 and time.monotonic()-sent>=1.:
                connection.write(encode(command)); attempts+=1; sent=time.monotonic()
    raise RuntimeError("wireless bench timeout; no verified applied/state result")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True); parser.add_argument("--timeout-s",type=float,default=10.)
    parser.add_argument("--simulate-shed",choices=["rail_2","rail_3"])
    parser.add_argument("--outputs-disconnected",action="store_true",help="operator confirms no relay/load wiring is attached")
    args=parser.parse_args()
    if args.simulate_shed and not args.outputs_disconnected: parser.error("--outputs-disconnected is required for a simulated command")
    if args.timeout_s<=0: parser.error("positive timeout required")
    try: print(json.dumps(run(args.port,args.simulate_shed,args.timeout_s),indent=2))
    except (OSError,RuntimeError) as exc: parser.exit(2,f"error: {exc}\n")


if __name__=="__main__": main()
