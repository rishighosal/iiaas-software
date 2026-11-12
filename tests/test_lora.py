import binascii
import pytest
from receiver.serial_receiver import parse_payload
from app.main import normalize

# Real packets copied from the Wio-E5 Dev Kit serial monitor (the hex after RX).
REAL = [
    "4E312C3231303533352C32372E36302C37352E30302C343039352C302C343039352C312C3234332C302E3139362C343030",
    "4E312C3232303633332C32372E36302C37352E30302C343039352C302C343039352C312C3234302C302E3139332C343030",
]


def test_real_n1_packet_decodes():
    text = binascii.unhexlify(REAL[0]).decode()
    assert text == "N1,210535,27.60,75.00,4095,0,4095,1,243,0.196,400"
    assert len(text) == 49  # the dev kit reported LEN:49


def test_real_packets_flow_into_normalize():
    for h in REAL:
        node, seq, d = normalize(parse_payload(binascii.unhexlify(h).decode()))
        assert node == 1 and d["air_temp"] == 27.6 and d["humidity"] == 75
        assert d["soil_moisture"] == 0 and d["relay"] is True and d["eco2_ppm"] == 400


def test_json_packets_still_work():
    assert parse_payload('{"id":1,"seq":5,"temp":30}')["seq"] == 5


@pytest.mark.parametrize("bad", ["N1,1,2,3", "N9,1,2", "hello", "N2,1,2"])
def test_wrong_packets_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_payload(bad)
