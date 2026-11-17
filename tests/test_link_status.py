"""Upgrade 4: link status."""
import pathlib, tempfile, time

import pytest
from fastapi.testclient import TestClient

import app.alerts as AL
import app.main as M

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
M.DB = AL.DB = pathlib.Path(tmp.name)
client = TestClient(M.app)


@pytest.fixture(autouse=True)
def empty():
    with M.db() as c:
        c.execute("DELETE FROM readings")


def add(node, secs_ago, rssi=None, source="lora"):
    with M.db() as c:
        c.execute("INSERT INTO readings(ts,node,seq,rssi,source,data) VALUES(?,?,?,?,?,?)",
                  (time.time() - secs_ago, node, None, rssi, source, "{}"))


def status():
    return client.get("/api/link-status").json()


def test_no_data_means_offline():
    j = status()
    assert j["overall"] == "offline"
    assert j["nodes"]["1"]["online"] is False and j["nodes"]["1"]["last_seen_s"] is None


def test_recent_packets_make_a_node_online_and_are_counted():
    for s in (2, 10, 30, 90, 600):
        add(1, s, rssi=-41.0)
    n1 = status()["nodes"]["1"]
    assert n1["online"] and n1["source"] == "lora" and n1["rssi"] == -41.0 and n1["signal"] == "strong"
    assert n1["packets_last_min"] == 3 and n1["packets_last_hour"] == 5 and n1["last_seen_s"] < 5


def test_overall_degraded_when_only_one_node_reports():
    add(1, 3, -50.0)
    add(2, 900, -50.0)  # last heard 15 minutes ago
    j = status()
    assert j["overall"] == "degraded" and j["nodes"]["2"]["online"] is False


def test_overall_ok_when_both_report():
    add(1, 3)
    add(2, 4, source="hub")
    j = status()
    assert j["overall"] == "ok" and j["nodes"]["2"]["source"] == "hub" and j["nodes"]["2"]["signal"] == "unknown"


@pytest.mark.parametrize("rssi,label", [(-41, "strong"), (-100, "strong"), (-110, "ok"), (-125, "weak"), (None, "unknown")])
def test_signal_labels(rssi, label):
    assert M.signal_label(rssi) == label


def test_signal_is_the_average_of_the_last_10_packets():
    for i in range(12):
        add(1, 100 - i, rssi=-30.0 if i < 2 else -50.0)  # the 2 oldest are -30, the newest 10 are -50
    assert status()["nodes"]["1"]["rssi"] == -50.0


def test_status_page_is_served():
    r = client.get("/status")
    assert r.status_code == 200 and "link status" in r.text
