"""Found with the real hardware: a DHT11 repeats the same air temperature for a long time (not a fault)."""
from app.anomaly import check


def rows(vals, step=5, field="soil_moisture"):
    return [{"ts": 1000 + i * step, field: v} for i, v in enumerate(vals)]


def msgs(r):
    return [i["msg"] for i in check(1, r)]


def test_constant_air_temperature_is_not_flagged():
    assert msgs(rows([27.6] * 400, field="air_temp")) == []  # 33 minutes of the same value


def test_constant_humidity_and_soil_temperature_are_not_flagged():
    assert msgs(rows([63] * 400, field="humidity")) == []
    assert msgs(rows([29.0] * 400, field="soil_temp")) == []


def test_soil_moisture_stuck_at_zero_is_flagged():
    assert any("soil moisture has not changed for 10 minutes" in m for m in msgs(rows([0] * 150)))


def test_ph_needs_30_minutes_before_it_is_flagged():
    assert msgs(rows([5.6] * 150, field="ph")) == []  # 12 minutes
    assert any("pH has not changed for 30 minutes" in m for m in msgs(rows([5.6] * 500, field="ph")))
