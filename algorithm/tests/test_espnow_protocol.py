import json
import subprocess
import importlib.util
from pathlib import Path
import pytest
from grid_algorithm.espnow import fragment,parse,Reassembler,HEADER,MAX_LINE,PAYLOAD
from grid_algorithm.protocol import encode,decode

PEER=bytes.fromhex("020000000002")


def receiver(): return Reassembler(1,101,PEER)


@pytest.mark.parametrize("length",[1,192,193,700,2048])
def test_fragment_roundtrip_maximum_and_reordering(length):
    raw=bytes(i%256 for i in range(length)); packets=fragment(raw,2,201,1,101)
    rx=receiver(); result=None
    for packet in reversed(packets):
        assert len(packet)<=250
        value=rx.accept(packet,0,PEER)
        if value is not None: result=value
    assert result==raw and len(rx.slots)==0


def test_largest_legal_canonical_message_and_json_validation():
    message=dict(v=1,type="diagnostic",source="esp32_bridge_01",event="x")
    base=len(encode(message)); message["event"]="x"*(2048-base+1)
    raw=encode(message); assert len(raw)==2048
    rx=receiver(); results=[rx.accept(p,0,PEER) for p in fragment(raw,2,201,1,101)]
    assert decode(results[-1])==message
    bad=fragment(b"not valid json\n",2,201,2,101)
    with pytest.raises(ValueError): decode(rx.accept(bad[0],0,PEER))


def test_loss_duplicates_timeout_recovery_and_capacity():
    raw=b"x"*700; packets=fragment(raw,2,201,1,101); rx=receiver()
    assert rx.accept(packets[0],0,PEER) is None
    assert rx.accept(packets[0],.1,PEER) is None and rx.duplicates==1
    rx.expire(1.5); assert rx.expired==1 and not rx.slots
    result=None
    for p in fragment(raw,2,201,2,101): result=rx.accept(p,2,PEER)
    assert result==raw
    for p in fragment(raw,2,201,2,101): assert rx.accept(p,2,PEER) is None
    for i in (3,4,5): rx.accept(fragment(raw,2,201,i,101)[0],2,PEER)
    assert len(rx.slots)==2 and rx.capacity_drops==1


@pytest.mark.parametrize("mutation",[lambda p:p.__setitem__(2,2),lambda p:p.__setitem__(4,2),
    lambda p:p.__setitem__(16,250),lambda p:p.__setitem__(17,250),lambda p:p.__setitem__(-1,p[-1]^1)])
def test_bad_envelope_or_crc(mutation):
    packet=bytearray(fragment(b"abc\n",2,201,1,101)[0]); mutation(packet)
    rx=receiver(); assert rx.accept(bytes(packet),0,PEER) is None and rx.errors==1


def test_invalid_peer_oversize_old_receiver_boot_and_conflicting_duplicate():
    packet=fragment(b"a"*700,2,201,1,101)[0]; rx=receiver()
    assert rx.accept(packet,0,b"\x02\x00\x00\x00\x00\x09") is None
    assert rx.accept(packet+b"x"*300,0,PEER) is None
    assert rx.accept(fragment(b"x",2,201,2,99)[0],0,PEER) is None
    rx.accept(packet,0,PEER)
    corrupt=bytearray(packet); corrupt[-1]^=1
    assert rx.accept(corrupt,0,PEER) is None and rx.errors==4
    with pytest.raises(ValueError): fragment(b"x"*2049,2,201,2,101)


def test_native_production_codec_golden_bytes():
    path=Path("algorithm/firmware/scripts/native_tests.py")
    spec=importlib.util.spec_from_file_location("grid_native",path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    try: binary=module.build()
    except RuntimeError as exc: pytest.skip(str(exc))
    for raw in (b"abc\n",b"a"*700,bytes(i%256 for i in range(2048))):
        expected=fragment(raw,2,201,42,101)
        native=subprocess.check_output([str(binary),"encode",raw.hex(),"2","201","42","101"],text=True).splitlines()
        assert native==[p.hex() for p in expected]
        decoded=subprocess.check_output([str(binary),"decode",*[p.hex() for p in reversed(expected)]],text=True).strip()
        assert bytes.fromhex(decoded)==raw
