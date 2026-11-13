"""Tests for upgrade 1 (data safety) and upgrade 2 (full CSV export)."""
import csv, io, pathlib, tempfile, time

import pytest
from fastapi.testclient import TestClient

import app.alerts as AL
import app.main as M

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
M.DB = AL.DB = pathlib.Path(tmp.name)
client = TestClient(M.app)
GOOD = {"node": "ESP32_1", "temperature": 28, "humidity": 60, "soil_percent": 50}


def test_normal_packet_is_accepted():
    assert client.post("/api/ingest", json=GOOD).status_code == 200


@pytest.mark.parametrize("field,value", [("temperature", -500), ("soil_percent", 999999), ("humidity", 5000)])
def test_impossible_values_are_rejected(field, value):
    r = client.post("/api/ingest", json={**GOOD, field: value})
    assert r.status_code == 422 and "impossible" in r.json()["detail"]


def test_suspicious_but_possible_value_is_still_stored():
    # soil 140% is wrong but possible after a sensor fault: store it so the anomaly check can flag it
    assert client.post("/api/ingest", json={**GOOD, "soil_percent": 140}).status_code == 200


def test_oversized_packet_is_rejected():
    r = client.post("/api/ingest", json={**GOOD, "junk": "x" * 5000})
    assert r.status_code == 413


def test_weird_source_label_is_cleaned():
    assert M.clean_source("<script>alert(1)</script>") == "device"
    assert M.clean_source("LoRa") == "lora"
    assert M.clean_source(None) == "device"


def test_api_key_is_enforced_only_when_set(monkeypatch):
    monkeypatch.setenv("IIAAS_KEY", "s3cret")
    assert client.post("/api/ingest", json=GOOD).status_code == 401
    assert client.post("/api/ingest", json=GOOD, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/api/ingest", json=GOOD, headers={"X-API-Key": "s3cret"}).status_code == 200
    monkeypatch.delenv("IIAAS_KEY")
    assert client.post("/api/ingest", json=GOOD).status_code == 200


def test_reading_endpoints_do_not_need_the_key(monkeypatch):
    monkeypatch.setenv("IIAAS_KEY", "s3cret")
    assert client.get("/api/latest").status_code == 200


def _fill(n):
    with M.db() as c:
        c.execute("DELETE FROM readings")
        now = time.time()
        for i in range(n):
            c.execute("INSERT INTO readings(ts,node,seq,rssi,source,data) VALUES(?,?,?,?,?,?)",
                      (now - (n - i) * 10, 1 + i % 2, i, -40.0, "sim", '{"soil_moisture": 50, "ph": 6.5}'))


def test_csv_export_has_no_row_limit():
    _fill(2600)
    rows = list(csv.reader(io.StringIO(client.get("/api/export.csv").text)))
    assert len(rows) == 2601 and rows[0][0] == "time_utc"  # header + every stored row (old limit was 2000)


def test_csv_export_filters():
    _fill(100)
    assert len(client.get("/api/export.csv?node=1").text.splitlines()) == 51
    assert len(client.get("/api/export.csv?hours=0.1").text.splitlines()) < 100  # 0.1 h = 6 min
    first = list(csv.DictReader(io.StringIO(client.get("/api/export.csv").text)))[0]
    assert first["time_utc"].endswith("+00:00") and first["source"] == "sim" and first["rssi"] == "-40.0"
