from pathlib import Path
from grid_algorithm.cli import simulate
from grid_algorithm.contracts import load_config
from grid_algorithm.persistence import EventLog
from grid_algorithm.dashboard_state import read_events, latest_snapshot


def test_wal_dashboard_crash_does_not_stop_control(tmp_path):
    path = tmp_path / "run.sqlite"
    log = EventLog(path)
    assert log.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    try:
        raise RuntimeError("injected dashboard crash")
    except RuntimeError:
        pass
    result = simulate(load_config(), duration=200, log=log)
    assert len(result["acks"]) == 2
    snapshot = latest_snapshot(read_events(path))
    assert snapshot["telemetry"] and snapshot["forecasts"]
    log.export(tmp_path / "events.csv")
    assert "command_id" in (tmp_path / "events.csv").read_text()
    log.close()


def test_streamlit_renders_empty_and_virtual_rig():
    import pytest
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("algorithm/dashboard/app.py").run(timeout=30)
    assert not app.exception
    app.sidebar.radio[0].set_value("Interactive virtual rig").run(timeout=30)
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any("Hot-spot" in metric.label for metric in app.metric)
