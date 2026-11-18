"""Read-only audit viewer plus isolated, explicitly virtual manual-control session."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "algorithm/src"), str(ROOT / "model/src")]
import streamlit as st
import pandas as pd
import numpy as np
from grid_algorithm.dashboard_state import read_events, latest_snapshot
from grid_algorithm.contracts import load_config
from grid_algorithm.simulator import Plant, RigController
from grid_algorithm.transport import FakeBridge
from grid_algorithm.policy import Policy
from grid_algorithm.coordinator import Coordinator
from grid_algorithm.persistence import EventLog
from grid_model.inference import Predictor
from grid_model.selection import select_model
from grid_model.physics_ieee import TransformerParameters
import json

st.set_page_config(page_title="IEEE x ADSC Heat Grid", layout="wide")
st.title("Heat Grid • IEEE × ADSC")
st.warning("DEMO / RESEARCH ONLY — laptop live control is monitor-only. Simulated state and radio-send success do not verify physical relay actuation.")
mode = st.sidebar.radio("Data source", ["Audit log", "Interactive virtual rig", "Oil-transformer analysis"])
path = st.sidebar.text_input("SQLite audit log", "algorithm/runs/demo.sqlite")
model_name = st.sidebar.selectbox("Forecast model", ["calibrated_rc", "ridge", "ieee_c57_91", "alliander_iec"])
artifact_path = st.sidebar.text_input("Ridge benchmark artifact", "model/artifacts/ridge-demo")
parameters_path = st.sidebar.text_input("Transformer parameters JSON", "model/configs/transformer.json")
calibration_path = st.sidebar.text_input("RC calibration JSON", "model/artifacts/rc-calibration/calibration.json")
show_warning_operating_point = st.sidebar.checkbox("Show validation-tuned Ridge early warnings", value=True)
oil_model = model_name in {"ieee_c57_91", "alliander_iec"}

if mode == "Oil-transformer analysis":
    st.subheader("Oil-transformer physics — analysis only")
    st.info("These parameters describe an illustrative oil-immersed transformer. They are never applied to the 12 V branches. No model here is physically commissioned.")
    if not oil_model:
        st.warning("Choose IEEE C57.91 or Alliander IEC for transformer analysis. Original Ridge and RC belong to the demo-rig domain.")
    else:
        load = st.number_input("Future load factor (per unit of rated current)", min_value=0., max_value=3., value=1.5, step=.1)
        initial_load = st.number_input("Prior equilibrium load factor", min_value=0., max_value=3., value=.7, step=.1)
        ambient = st.number_input("Ambient temperature (°C)", min_value=-50., max_value=60., value=30.)
        try:
            predictor = select_model(model_name, parameters=parameters_path)
            from grid_model.crossing import first_crossing
            result = predictor.profile(np.arange(301), [initial_load]+[load]*300, [ambient]*301)
            st.write(f"Model: {result['model']} · edition: {result['edition']}")
            st.dataframe([dict(horizon_s=h, top_oil_c=result["top_oil_c"][h], hotspot_c=result["hotspot_c"][h]) for h in (60,300)])
            eta = first_crossing(result["times_s"], result["hotspot_c"], predictor.parameters.threshold_c)
            st.write(f"Threshold: {predictor.parameters.threshold_c} °C · estimated crossing: {eta if eta is not None else 'outside 300s/unknown'} s")
            if eta is not None: st.warning("Predicted transformer temperature threshold crossing (analysis warning only).")
            if "equivalent_aging_h" in result: st.write(f"IEEE equivalent aging over forecast: {result['equivalent_aging_h']:.5f} h at 110°C reference")
            st.line_chart(pd.DataFrame(dict(top_oil=result["top_oil_c"],hotspot=result["hotspot_c"]),index=result["times_s"]))
            st.caption(result["limitations"]+"; uncertainty is not calibrated. No physical relay commands are generated.")
        except (ImportError, OSError, ValueError) as exc: st.error(str(exc))
    st.stop()

if mode == "Audit log": st.sidebar.caption("Logged forecasts retain their original model identity; selecting a model does not rewrite history.")

if mode == "Interactive virtual rig":
    if "rig" not in st.session_state:
        config = load_config(ROOT / "algorithm/fixtures/rail_config.csv")
        plant = Plant(config); controller = RigController(plant)
        log = EventLog(ROOT / "algorithm/runs/dashboard.sqlite")
        app = Coordinator(config, select_model("calibrated_rc"), Policy(config), FakeBridge(controller), log)
        st.session_state.rig = (plant, controller, app)
    plant, controller, app = st.session_state.rig
    path = str(ROOT / "algorithm/runs/dashboard.sqlite")
    if oil_model:
        st.error("Oil-transformer model selected: demo-rig actuation and advancement blocked. Use Oil-transformer analysis.")
    else:
        app.predictor = select_model(model_name,artifact_path,calibration=calibration_path if Path(calibration_path).is_file() else None)
    if st.button("Advance virtual rig 60 seconds", disabled=oil_model):
        for _ in range(60):
            app.accept(app.transport.telemetry(), plant.time)
            app.tick(plant.time); plant.step()
    st.sidebar.caption(f"Virtual time: {plant.time:.0f}s")
    st.subheader("Supervised virtual restoration")
    rid = st.selectbox("Eligible branch", ["rail_2", "rail_3"])
    operator = st.text_input("Operator identity")
    consent = st.checkbox("I authorize restoring this simulated load")
    safe = controller.safe_to_restore(rid) and app.policy.state[rid] == "SHED_CONFIRMED"
    if st.button("Restore simulated branch", disabled=oil_model or not (safe and consent and operator.strip())):
        cmd = app.policy.manual_restore(rid, plant.time, operator.strip(), controller.safe_to_restore(rid))
        app.send(cmd, plant.time)
        st.success("Request logged; controller applies its own cooldown and sensor checks.")
    st.caption("Restoration requires an operator, confirmed off state, cooldown and controller safety check. No physical controls are exposed.")

@st.fragment(run_every=2.0)
def render():
    events = read_events(path)
    if not events:
        st.info("Run python -m grid_algorithm simulate, or advance the interactive virtual rig.")
        return
    snapshot = latest_snapshot(events)
    run = snapshot["run_metadata"]; serial = snapshot["serial_status"]; bridge = snapshot["bridge_status"]
    st.caption(f"Data source: {run.get('mode','historical/unspecified')} · transport: {run.get('transport','unspecified')}")
    if serial: st.write(f"Laptop ↔ bridge USB: {'connected' if serial.get('connected') else 'disconnected'} · {serial.get('port')} · monitor only: {serial.get('monitor_only')}")
    if bridge:
        st.write(f"Bridge ↔ controller ESP-NOW: initialized={bridge.get('link_initialized')} · peer configured={bridge.get('peer_configured')} · recently heard={bridge.get('peer_recent')} · channel={bridge.get('channel')}")
        st.caption(f"Bridge station MAC: {bridge.get('local_mac')} · encryption={bridge.get('encrypted')} · reported RX age={bridge.get('last_rx_age_ms')}ms · fragment errors={bridge.get('fragment_errors')} · timeouts={bridge.get('reassembly_timeouts')}")
        if not bridge.get("peer_recent"): st.error("ESP-NOW peer missing or stale; radio-level delivery is not a controller-applied ACK.")
    frame = snapshot["telemetry"]
    if frame is None: return
    st.caption(f"Controller sensors: {'simulated' if frame.get('simulated_sensors',run.get('simulated_sensors')) is True else 'reported measurements / mode unverified'} · physical outputs: {'firmware reports enabled; electrical state unverified' if frame.get('physical_outputs_enabled') is True else 'disabled or unverified'}")
    from datetime import datetime, timezone
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot["telemetry_utc"] or events[-1]["utc"])).total_seconds()
    st.caption(f"Last controller telemetry: {age:.1f}s ago. Link states above are last reported; completed/replayed logs are historical. Device uptime is not UTC.")
    if age > 5: st.warning("No fresh controller telemetry in 5s: historical/completed run, disconnected producer or failed radio link.")
    if frame["fault_flags"] or snapshot["faults"]:
        st.error(f"Sensor/link faults: {frame['fault_flags']} {snapshot['faults'][-3:]}")
    config = load_config(ROOT / "algorithm/fixtures/rail_config.csv")
    for column, rail in zip(st.columns(len(frame["rails"])), frame["rails"]):
        with column:
            rid = rail["id"]; forecast = snapshot["forecasts"].get(rid, {})
            if rid not in config:
                st.error(f"Unconfigured rail {rid}; no control state is trusted."); continue
            st.subheader(rid)
            t = rail["hotspot_c"]
            st.metric("Hot-spot proxy", "unavailable" if t is None else f"{t:.2f} °C")
            st.write(f"Relay: {'ON' if rail['enabled'] else 'OFF'} · {snapshot['state'].get('states', {}).get(rid, 'UNKNOWN')}")
            st.write(f"Current: {rail['a']} A · voltage: {rail['v']} V · ambient: {frame['ambient_temp_c']} °C")
            st.write(f"Model: {forecast.get('model_id', 'unknown')} · quality: {forecast.get('data_quality', 'invalid')}")
            st.caption(forecast.get("limitation", "Uncertainty not calibrated"))
            predicted = forecast.get("predicted_hotspot_plus_300s_c")
            if forecast.get("data_quality") == "good" and predicted is not None and predicted >= config[rid].warning:
                st.warning("Predicted no-intervention warning threshold within 300s")
            warning_file = ROOT / "model/reports/detection-comparison/comparison.json"
            if show_warning_operating_point and forecast.get("model_id") == "ridge" and forecast.get("data_quality") == "good" and warning_file.is_file():
                operating = json.loads(warning_file.read_text()).get("ridge_early_warning", {})
                cutoff = operating.get("forecast_warning_cutoff_c")
                values = [forecast.get(f"predicted_hotspot_plus_{h}s_c") for h in (60,300)]
                if cutoff is not None and all(v is not None for v in values) and max(values) >= cutoff:
                    st.warning(f"Advisory early warning: forecast ≥ {cutoff:.2f}°C operating point for an 80°C event. Not a new safety limit or confidence percentage.")
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
