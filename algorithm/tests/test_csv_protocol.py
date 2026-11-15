import csv
import json
import pytest
from grid_algorithm.contracts import from_csv, to_long, from_long, to_csv, command_from_csv, ack_from_csv, boolean
from grid_algorithm.protocol import encode, decode, Framer


def fixture():
    with open("algorithm/fixtures/esp32_telemetry_replay.csv") as stream: return from_csv(next(csv.DictReader(stream))).to_dict()


def test_roundtrip_all_fixtures():
    frame = fixture()
    assert decode(encode(frame)) == frame
    rows = to_long(frame, 10)
    assert len(rows) == 3 and {r["t_s"] for r in rows} == {10}
    for name, adapter in [("commands", command_from_csv), ("acks", ack_from_csv)]:
        with open(f"algorithm/fixtures/esp32_control_{name}.csv") as stream:
            converted = [adapter(row) for row in csv.DictReader(stream)]
        assert len(converted) == 3
        for message in converted: assert decode(encode(message)) == message
    assert boolean("0") is False and boolean("1") is True


def test_wide_long_roundtrip_and_mixed_time_rejected():
    frame = fixture()
    rows = to_long(frame, 10)
    rebuilt = from_long(rows, frame["source"], frame["seq"], frame["uptime_ms"], frame["fault_flags"], frame["last_applied_command_id"])
    assert rebuilt == frame
    assert from_csv(to_csv(frame, "2026-10-19T20:00:00Z")).to_dict() == frame
    rows[0]["t_s"] = 11
    with pytest.raises(ValueError): from_long(rows, frame["source"], 1, 0)


@pytest.mark.parametrize("mutator", [lambda x: x.update(v=2), lambda x: x.update(seq=-1),
    lambda x: x["rails"].append(x["rails"][0]), lambda x: x["rails"][0].update(a=100),
    lambda x: x["rails"][0].update(hotspot_c=float("nan")), lambda x: x["rails"][0].update(enabled="0")])
def test_bad_frame_rejected(mutator):
    frame = fixture(); mutator(frame)
    with pytest.raises(ValueError): encode(frame)


@pytest.mark.parametrize("raw", [b"bad\n", b"{}\n", b'{"v":1,"v":1}\n', b"x" * 2049 + b"\n"])
def test_bad_json(raw):
    with pytest.raises(ValueError): decode(raw)


def test_framer_resynchronizes():
    raw = encode(fixture()); parser = Framer()
    assert parser.feed(b"x" * 3000 + b"\n" + raw[:10]) == []
    assert parser.feed(raw[10:]) == [fixture()]
    assert parser.errors == 1
