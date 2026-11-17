"""Upgrade 3: crop profiles and settings."""
import pathlib, tempfile

import pytest
from fastapi.testclient import TestClient

import app.alerts as AL
import app.main as M

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
M.DB = AL.DB = pathlib.Path(tmp.name)
client = TestClient(M.app)


@pytest.fixture(autouse=True)
def reset():
    client.post("/api/settings", json={"crop": "general"})
    yield
    client.post("/api/settings", json={"crop": "general"})


def msgs():
    return [i["msg"] for i in client.get("/api/insights").json()]


def put(node, **kw):
    assert client.post("/api/ingest", json={"node": node, **kw}).status_code == 200


def test_default_is_general():
    j = client.get("/api/settings").json()
    assert j["crop"] == "general" and j["thresholds"]["moist_low"] == 40 and "tea" in j["crops"]


def test_choosing_tea_changes_the_ph_advice():
    put("ESP32_2", temperature=26, moisture=55, ph=6.5, nitrogen=80, phosphorus=30, potassium=130)
    assert not any("alkaline" in m for m in msgs())          # fine for the general profile
    r = client.post("/api/settings", json={"crop": "tea"}).json()
    assert r["thresholds"]["ph_low"] == 4.5 and r["thresholds"]["ph_high"] == 5.5
    assert any("alkaline" in m for m in msgs())              # too high for tea


def test_rice_needs_wetter_soil():
    put("ESP32_1", temperature=28, humidity=60, soil_percent=50, relay=False)
    assert not any("Irrigate" in m for m in msgs())
    client.post("/api/settings", json={"crop": "rice"})
    assert any("below 60%" in m and "Irrigate" in m for m in msgs())


def test_custom_value_is_saved_and_a_new_crop_clears_it():
    r = client.post("/api/settings", json={"crop": "wheat", "overrides": {"moist_low": 55}}).json()
    assert r["thresholds"]["moist_low"] == 55 and r["overrides"] == {"moist_low": 55.0}
    assert M.read_settings()["crop"] == "wheat"              # stored in the database, survives a restart
    r = client.post("/api/settings", json={"crop": "potato"}).json()
    assert r["thresholds"]["moist_low"] == 50 and r["overrides"] == {}


@pytest.mark.parametrize("body", [
    {"crop": "banana"},
    {"overrides": {"colour": 1}},
    {"overrides": {"ph_high": 20}},
    {"overrides": {"moist_low": "lots"}},
    {"overrides": {"moist_low": True}},
    {"overrides": {"moist_low": 90, "moist_high": 50}},
])
def test_bad_settings_are_rejected(body):
    assert client.post("/api/settings", json=body).status_code == 422


def test_rejected_settings_do_not_change_anything():
    client.post("/api/settings", json={"crop": "tea"})
    client.post("/api/settings", json={"overrides": {"moist_low": 90, "moist_high": 50}})
    assert client.get("/api/settings").json()["crop"] == "tea"


def test_settings_page_is_served():
    r = client.get("/settings")
    assert r.status_code == 200 and "IIAAS settings" in r.text
