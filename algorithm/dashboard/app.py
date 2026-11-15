"""Read-only audit viewer plus isolated, explicitly virtual manual-control session."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "algorithm/src"), str(ROOT / "model/src")]
import streamlit as st
import pandas as pd
from grid_algorithm.dashboard_state import read_events, latest_snapshot
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.persistence import EventLog
from grid_model.inference import Predictor

st.set_page_config(page_title="IEEE x ADSC Heat Grid", layout="wide")
st.title("Heat Grid • IEEE × ADSC")
st.warning("SYNTHETIC / DEMO ONLY — not a validated transformer protection system. Physical relay control disabled.")
mode = st.sidebar.radio("Data source", ["Audit log", "Interactive virtual rig"])
path = st.sidebar.text_input("SQLite audit log", "algorithm/runs/demo.sqlite")

if mode == "Interactive virtual rig":
    if "rig" not in st.session_state:
        config = load_config(ROOT / "algorithm/fixtures/rail_config.csv")
        plant = Plant(config); controller = RigController(plant)
        log = EventLog(ROOT / "algorithm/runs/dashboard.sqlite")
        app = Coordinator(config, Predictor(), Policy(config), FakeBridge(controller), log)
        st.session_state.rig = (plant, controller, app)
    plant, controller, app = st.session_state.rig
    path = str(ROOT / "algorithm/runs/dashboard.sqlite")
    if st.button("Advance virtual rig 60 seconds"):
        for _ in range(60):
            app.accept(app.transport.telemetry(), plant.time)
            app.tick(plant.time); plant.step()
    st.sidebar.caption(f"Virtual time: {plant.time:.0f}s")
    st.subheader("Supervised virtual restoration")
    rid = st.selectbox("Eligible branch", ["rail_2", "rail_3"])
    operator = st.text_input("Operator identity")
    consent = st.checkbox("I authorize restoring this simulated load")
    safe = controller.safe_to_restore(rid) and app.policy.state[rid] == "SHED_CONFIRMED"
    if st.button("Restore simulated branch", disabled=not (safe and consent and operator.strip())):
        cmd = app.policy.manual_restore(rid, plant.time, operator.strip(), controller.safe_to_restore(rid))
        app.send(cmd, plant.time)
        st.success("Request logged; controller applies its own cooldown and sensor checks.")
    st.caption("Restoration requires an operator, confirmed off state, cooldown and controller safety check. No physical controls are exposed.")

@st.fragment(run_every="2s")
def render():
    events = read_events(path)
    if not events:
        st.info("Run python -m grid_algorithm simulate, or advance the interactive virtual rig.")
        return
    snapshot = latest_snapshot(events)
    frame = snapshot["telemetry"]
    if frame is None: return
    from datetime import datetime, timezone
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(events[-1]["utc"])).total_seconds()
    st.caption(f"Last writer activity: {age:.1f}s ago. Completed/replayed logs are historical; device uptime is not UTC.")
    if age > 5: st.warning("No fresh ingestion in 5s: historical/completed run or disconnected producer.")
    if frame["fault_flags"] or snapshot["faults"]:
        st.error(f"Sensor/link faults: {frame['fault_flags']} {snapshot['faults'][-3:]}")
    config = load_config(ROOT / "algorithm/fixtures/rail_config.csv")
    for column, rail in zip(st.columns(len(frame["rails"])), frame["rails"]):
        with column:
            rid = rail["id"]; forecast = snapshot["forecasts"].get(rid, {})
            st.subheader(rid)
            t = rail["hotspot_c"]
            st.metric("Hot-spot proxy", "unavailable" if t is None else f"{t:.2f} °C")
            st.write(f"Relay: {'ON' if rail['enabled'] else 'OFF'} · {snapshot['state'].get('states', {}).get(rid, 'UNKNOWN')}")
            st.write(f"Current: {rail['a']} A · voltage: {rail['v']} V · ambient: {frame['ambient_temp_c']} °C")
            st.write(f"Model: {forecast.get('model_id', 'unknown')} · quality: {forecast.get('data_quality', 'invalid')}")
            for horizon in (60, 300):
                value = forecast.get(f"predicted_hotspot_plus_{horizon}s_c")
                st.write(f"+{horizon}s: {'unavailable' if value is None else f'{value:.2f} °C'}")
            eta = forecast.get("eta_to_80c_s")
            st.write("ETA to 80°C: unknown/outside horizon" if eta is None else f"RC constant-load ETA: {eta:.0f}s")
            if t is None or not rail["sensor_valid"]: st.error("Sensor invalid")
            elif t >= config[rid].critical: st.error("Critical")
            elif t >= config[rid].warning: st.warning("Warning")
            rows = []
            for event in events:
                if event["kind"] == "forecast" and event["payload"]["rail_id"] == rid:
                    f = event["payload"]
                    rows.append({"time_s": event["t_s"], "observed": f["observed_hotspot_c"],
                                 "+60s": f["predicted_hotspot_plus_60s_c"], "+300s": f["predicted_hotspot_plus_300s_c"]})
            if rows: st.line_chart(pd.DataFrame(rows).set_index("time_s"))
    st.subheader("Command, ACK and fault audit")
    st.dataframe([dict(t_s=e["t_s"], kind=e["kind"], detail=str(e["payload"])) for e in events if e["kind"] in {"command", "ack", "fault", "error", "reboot"}])
    st.caption("Predictions assume no future intervention. No calibrated confidence percentage is available.")

render()
