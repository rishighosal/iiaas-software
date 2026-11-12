"""IIAAS Software Demonstration Simulator.

Sends simulated sensor readings (source="sim") to POST /api/ingest.
Supports multiple demonstration scenarios to reliably test and demo the entire
software stack without requiring physical ESP32 or sensor hardware.

Scenarios:
  normal        - Gradual realistic drift; soil moisture stays within 33-70% (default).
  low-moisture  - Low soil moisture (<40%), triggers irrigation alert and pump relay ON.
  high-temp     - High air temperature (>38°C), triggers heat stress warning.
  abnormal-ph   - Extreme soil pH (acidic 4.8 or alkaline 8.5), triggers soil treatment warning.
  pump-cycle    - Alternates pump relay ON/OFF every few iterations to demonstrate pump event history.
  critical      - Combo of low moisture, high temp, and abnormal pH for full system alert demo.

All packets are explicitly tagged source="sim" and alerts are logged with channel="sim"
so simulated readings are never represented as real hardware data.
"""

import argparse
import json
import random
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "iiaas.db"

ap = argparse.ArgumentParser(description="IIAAS Demonstration Simulator")
ap.add_argument("--url", default="http://localhost:8000/api/ingest", help="Ingest API URL")
ap.add_argument("--scenario", default="normal",
                choices=["normal", "low-moisture", "high-temp", "abnormal-ph", "pump-cycle", "critical"],
                help="Demonstration scenario to run (default: normal)")
ap.add_argument("--count", type=int, default=0, help="Number of packets to send (0 = run forever)")
ap.add_argument("--every", type=float, default=2.0, help="Seconds between packets (default: 2.0s)")
a = ap.parse_args()


def post(p):
    req = urllib.request.Request(a.url, json.dumps(p).encode(), {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5)


def ensure_alerts_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, ts REAL, node INT, level TEXT, "
              "msg TEXT, channel TEXT, sent INT, acked INT DEFAULT 0)")
    try:
        c.execute("ALTER TABLE alerts ADD COLUMN acked INT DEFAULT 0")
    except sqlite3.OperationalError:
        pass


_last_sim_alert = {}


def log_simulated_alert(node: int, level: str, msg: str):
    """Persists a simulated alert to the alerts table so acknowledgment can be demonstrated."""
    key = re.sub(r"[\d.]+", "#", msg)
    now = time.time()
    # 60-second cooldown per alert key to prevent flooding SQLite
    if now - _last_sim_alert.get(key, 0) < 60:
        return
    _last_sim_alert[key] = now
    try:
        with sqlite3.connect(DB) as c:
            ensure_alerts_table(c)
            c.execute("INSERT INTO alerts(ts,node,level,msg,channel,sent,acked) VALUES(?,?,?,?,?,?,0)",
                      (now, node, level, msg, "sim", 0))
        print(f"  [SIMULATOR ALERT LOGGED] ({level.upper()}) {msg}")
    except Exception as ex:
        print(f"  [SIMULATOR ALERT DB ERROR] {ex}")


print("=" * 65)
print("  IIAAS DEMONSTRATION SIMULATOR")
print(f"  Scenario : {a.scenario.upper()}")
print(f"  Target   : {a.url}")
print(f"  Interval : {a.every}s | Count: {'Infinite' if a.count == 0 else a.count}")
print("  Notice   : ALL DATA IS SYNTHETIC (source='sim')")
print("=" * 65)

m1, m2 = 58.0, 52.0
i = 0
pump_state = False

while a.count == 0 or i < a.count:
    i += 1
    now = time.time()

    if a.scenario == "normal":
        m1 += random.uniform(-3, 1)
        m2 += random.uniform(-2, 1)
        if m1 < 33:
            m1 = 70.0
        if m2 < 30:
            m2 = 65.0
        n1_temp = round(random.uniform(28, 33), 1)
        n1_hum = round(random.uniform(55, 75))
        n1_soil = int(m1)
        n1_relay = n1_soil < 40
        n2_temp = round(random.uniform(25, 29), 1)
        n2_soil = round(m2, 1)
        n2_ph = round(6.4 + random.uniform(-0.3, 0.3), 1)

    elif a.scenario == "low-moisture":
        # Simulate dry soil below 40% threshold, pump turns ON to irrigate
        n1_soil = random.randint(28, 35)
        n1_relay = True
        n1_temp = round(random.uniform(30, 34), 1)
        n1_hum = round(random.uniform(40, 55))
        n2_soil = round(random.uniform(30, 36), 1)
        n2_temp = round(random.uniform(26, 30), 1)
        n2_ph = 6.5
        log_simulated_alert(1, "bad", f"Node 1: soil moisture {n1_soil}% is below 40%. Irrigate.")

    elif a.scenario == "high-temp":
        # Simulate excessive heat > 38°C triggering heat stress alert
        n1_temp = round(random.uniform(39.0, 42.5), 1)
        n1_hum = round(random.uniform(35, 50))
        n1_soil = random.randint(45, 55)
        n1_relay = False
        n2_temp = round(random.uniform(34, 37), 1)
        n2_soil = round(random.uniform(45, 55), 1)
        n2_ph = 6.6
        log_simulated_alert(1, "warn", f"Node 1: air temperature {n1_temp} °C. Heat stress risk.")

    elif a.scenario == "abnormal-ph":
        # Alternates between acidic (<5.5) and alkaline (>7.5) soil.
        # Abnormal pH is an agronomic condition displayed in the Recommendations card via /api/insights,
        # rather than an emergency alert in the alerts table.
        n2_ph = 4.8 if (i % 6 < 3) else 8.4
        n1_soil = 52
        n1_relay = False
        n1_temp = 29.5
        n1_hum = 65
        n2_temp = 27.0
        n2_soil = 50.0

    elif a.scenario == "pump-cycle":
        # Alternate pump relay state every 3 readings so transitions are clear
        pump_state = (i // 3) % 2 == 1
        n1_soil = 34 if pump_state else 62
        n1_relay = pump_state
        n1_temp = 29.0
        n1_hum = 65
        n2_soil = 48.0
        n2_temp = 26.5
        n2_ph = 6.5
        if pump_state:
            log_simulated_alert(1, "bad", f"Node 1: soil moisture {n1_soil}% is below 40%. Irrigate.")

    elif a.scenario == "critical":
        # Combined crisis scenario: low soil moisture and extreme heat generate separate alerts.
        # Abnormal pH (4.9) is sent in Node 2 telemetry and rendered as agronomic guidance in Recommendations.
        n1_soil = 31
        n1_relay = True
        n1_temp = 40.2
        n1_hum = 38
        n2_soil = 32.0
        n2_temp = 35.0
        n2_ph = 4.9
        log_simulated_alert(1, "bad", f"Node 1: soil moisture {n1_soil}% is below 40%. Irrigate.")
        log_simulated_alert(1, "warn", f"Node 1: air temperature {n1_temp} °C. Heat stress risk.")

    p1 = {
        "node": "ESP32_1",
        "temperature": n1_temp,
        "humidity": n1_hum,
        "soil_percent": n1_soil,
        "water_level_raw": random.randint(1800, 2400),
        "mq135_raw": random.randint(650, 850),
        "eco2_ppm": random.randint(450, 600),
        "relay": n1_relay,
        "source": "sim"
    }

    p2 = {
        "node": "ESP32_2",
        "temperature": n2_temp,
        "moisture": n2_soil,
        "ph": n2_ph,
        "nitrogen": random.randint(40, 85),
        "phosphorus": random.randint(15, 35),
        "potassium": random.randint(90, 150),
        "count": i * 5,
        "source": "sim"
    }

    try:
        post(p1)
        post(p2)
        print(f"[{time.strftime('%H:%M:%S')}] #{i} Sent: Node 1 (Soil {n1_soil}%, Temp {n1_temp}°C, Pump {'ON' if n1_relay else 'OFF'}) | Node 2 (pH {n2_ph}) [SIMULATED]")
    except Exception as ex:
        print(f"[{time.strftime('%H:%M:%S')}] #{i} Post failed: {ex}")

    time.sleep(a.every)
