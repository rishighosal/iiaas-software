"""Comprehensive integration test suite covering all backend APIs and features."""
import sys, json, time, sqlite3, tempfile, pathlib, os
sys.path.insert(0, '.')

import app.main as M
import app.alerts as AL
from fastapi import HTTPException

# Create isolated test database
tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
tmp.close()
tmppath = pathlib.Path(tmp.name)
M.DB = tmppath
AL.DB = tmppath

def test_integration_suite():
    # 1. Ingest tests
    with M.db() as c:
        c.execute('DELETE FROM readings')

    # Ingest Hub format Node 1
    r1 = M.ingest({"node": "ESP32_1", "temperature": 31.2, "humidity": 65, "soil_percent": 38,
                   "water_level_raw": 2100, "mq135_raw": 720, "eco2_ppm": 480, "relay": True, "source": "sim"})
    assert r1["ok"] is True and r1["node"] == 1, "Failed Hub format Node 1 ingest"

    # Ingest Hub format Node 2
    r2 = M.ingest({"node": "ESP32_2", "temperature": 26.5, "moisture": 45, "ph": 6.8,
                   "nitrogen": 70, "phosphorus": 30, "potassium": 140, "count": 12, "source": "sim"})
    assert r2["ok"] is True and r2["node"] == 2, "Failed Hub format Node 2 ingest"

    # Ingest Compact LoRa format
    r3 = M.ingest({"id": 1, "seq": 108, "temp": 30.0, "hum": 62, "soil": 55, "relay": False, "source": "device"})
    assert r3["ok"] is True and r3["node"] == 1, "Failed compact LoRa format ingest"

    print("PASS 1: Ingest endpoints accepted both Hub and LoRa payloads")

    # 2. Latest API test
    latest_data = M.api_latest()
    assert "now" in latest_data and "nodes" in latest_data, "Malformed latest response"
    assert 1 in latest_data["nodes"] and 2 in latest_data["nodes"], "Missing nodes in latest"
    assert latest_data["nodes"][1]["data"]["soil_moisture"] == 55, "Wrong Node 1 latest value"
    assert latest_data["nodes"][2]["data"]["ph"] == 6.8, "Wrong Node 2 latest value"
    print("PASS 2: /api/latest returns normalized multi-node data")

    # 3. Insights API test
    insights = M.insights()
    assert isinstance(insights, list) and len(insights) > 0, "Empty insights"
    assert any(i.get("level") in ("ok", "warn", "bad", "info") for i in insights), "Invalid insight level"
    print("PASS 3: /api/insights generates rule-based recommendations")

    # 4. History API tests (1h, 24h, all-time, node filter)
    now = time.time()
    test_readings = [
        # 2 days ago (> 24h)
        (now - 172800, 1, 1, None, 'sim', json.dumps({'soil_moisture': 60, 'relay': False})),
        # 12 hours ago (> 1h, <= 24h)
        (now - 43200, 1, 2, None, 'sim', json.dumps({'soil_moisture': 50, 'relay': False})),
        # 30 minutes ago (<= 1h)
        (now - 1800, 1, 3, None, 'sim', json.dumps({'soil_moisture': 42, 'relay': False})),
        # 5 minutes ago (<= 1h)
        (now - 300, 1, 4, None, 'sim', json.dumps({'soil_moisture': 38, 'relay': True})),
        # 1 minute ago (Node 2)
        (now - 60, 2, 5, None, 'sim', json.dumps({'soil_moisture': 45, 'ph': 6.5})),
    ]
    with M.db() as c:
        c.execute('DELETE FROM readings')
        for row in test_readings:
            c.execute('INSERT INTO readings(ts,node,seq,rssi,source,data) VALUES(?,?,?,?,?,?)', row)

    # All-time
    h_all = M.history(limit=100)
    assert len(h_all) == 5, f"Expected 5 all-time rows, got {len(h_all)}"

    # Node 1 only
    h_node1 = M.history(node=1, limit=100)
    assert len(h_node1) == 4, f"Expected 4 Node 1 rows, got {len(h_node1)}"

    # Node 2 only
    h_node2 = M.history(node=2, limit=100)
    assert len(h_node2) == 1, f"Expected 1 Node 2 row, got {len(h_node2)}"

    # 24 Hours filter (should exclude 2-day-old reading)
    h_24h = M.history(hours=24, limit=100)
    assert len(h_24h) == 4, f"Expected 4 rows within 24h, got {len(h_24h)}"

    # 1 Hour filter (should only include 30m, 5m, 1m readings)
    h_1h = M.history(hours=1, limit=100)
    assert len(h_1h) == 3, f"Expected 3 rows within 1h, got {len(h_1h)}"

    print("PASS 4: /api/history time filters (1h, 24h, all) and node filters work accurately")

    # 5. Pump Events API test (relay transitions + duration)
    pump_sequence = [
        (now - 600, 1, 10, None, 'sim', json.dumps({'soil_moisture': 55, 'relay': False})),
        (now - 500, 1, 11, None, 'sim', json.dumps({'soil_moisture': 38, 'relay': True})),   # ON transition
        (now - 400, 1, 12, None, 'sim', json.dumps({'soil_moisture': 40, 'relay': True})),   # Still ON
        (now - 260, 1, 13, None, 'sim', json.dumps({'soil_moisture': 52, 'relay': False})),  # OFF transition (ran 240s)
        (now - 100, 1, 14, None, 'sim', json.dumps({'soil_moisture': 36, 'relay': True})),   # Second ON transition
    ]
    with M.db() as c:
        c.execute('DELETE FROM readings')
        for row in pump_sequence:
            c.execute('INSERT INTO readings(ts,node,seq,rssi,source,data) VALUES(?,?,?,?,?,?)', row)

    events = M.pump_events(limit=50)
    assert len(events) == 3, f"Expected 3 events (ON, OFF, ON), got {len(events)}"
    assert events[0]["event"] == "on", f"Most recent event should be 'on', got {events[0]['event']}"
    assert events[0]["duration_s"] is None, "Active ON event should not have a completed duration"
    assert events[1]["event"] == "off", f"Second event should be 'off', got {events[1]['event']}"
    assert events[1]["duration_s"] == 240.0, f"Expected duration 240.0s, got {events[1]['duration_s']}"
    assert events[2]["event"] == "on", f"Third event should be 'on', got {events[2]['event']}"

    print("PASS 5: /api/pump-events accurately detects ON/OFF transitions and computes duration")

    # 6. CSV Export test
    csv_resp = M.export_csv()
    csv_body = csv_resp.body.decode('utf-8')
    assert "soil_moisture" in csv_body and "relay" in csv_body, "CSV missing expected headers"
    assert len(csv_body.splitlines()) > 1, "CSV missing data rows"
    print("PASS 6: /api/export.csv generates valid CSV with all sensor headers")

    # 7. Static file routes (index, sw.js, manifest.json)
    idx = M.index()
    assert os.path.exists(idx.path), "index.html missing"
    sw_resp = M.sw()
    assert os.path.exists(sw_resp.path), "sw.js missing"
    mf_resp = M.manifest()
    assert os.path.exists(mf_resp.path), "manifest.json missing"
    print("PASS 7: Static file endpoints (/ , /sw.js, /manifest.json) resolve to valid files")

    # 8. Alerts API tests (logging, filtering active, acknowledging)
    with sqlite3.connect(AL.DB) as c:
        AL.ensure(c)
        c.execute('DELETE FROM alerts')
        # Insert unacknowledged alert 5 mins ago
        c.execute("INSERT INTO alerts(ts,node,level,msg,channel,sent,acked) VALUES(?,?,?,?,?,?,0)",
                  (now - 300, 1, "bad", "Node 1: soil moisture 35% is below 40%. Irrigate.", "log", 0))
        # Insert unacknowledged alert 40 mins ago (> 30 min ACTIVE_S threshold)
        c.execute("INSERT INTO alerts(ts,node,level,msg,channel,sent,acked) VALUES(?,?,?,?,?,?,0)",
                  (now - 2400, 2, "warn", "Node 2: soil is acidic (pH 5.2).", "log", 0))
        # Insert acknowledged alert 10 mins ago
        c.execute("INSERT INTO alerts(ts,node,level,msg,channel,sent,acked) VALUES(?,?,?,?,?,?,1)",
                  (now - 600, 1, "warn", "Node 1: air temperature 39.0 °C. Heat stress risk.", "log", 0))

    # List all alerts
    alerts_all = AL.list_alerts(active=0)
    assert len(alerts_all) == 3, f"Expected 3 total alerts, got {len(alerts_all)}"

    # List active alerts (should only return the unacked alert within 30 min)
    alerts_active = AL.list_alerts(active=1)
    assert len(alerts_active) == 1, f"Expected 1 active alert, got {len(alerts_active)}"
    active_id = alerts_active[0]["id"]

    # Acknowledge the active alert
    ack_res = AL.ack_alert(active_id)
    assert ack_res.get("ok") is True, "Failed to acknowledge alert"

    # Verify it is no longer returned in active=1
    alerts_active_after = AL.list_alerts(active=1)
    assert len(alerts_active_after) == 0, "Acknowledged alert still returned in active list"

    # Acknowledging invalid alert ID must raise 404
    try:
        AL.ack_alert(99999)
        assert False, "Should have raised HTTPException 404"
    except HTTPException as e:
        assert e.status_code == 404

    print("PASS 8: /api/alerts filtering and /api/alerts/{id}/ack workflow validated")

    # Clean up
    try:
        os.unlink(tmp.name)
    except PermissionError:
        pass

if __name__ == "__main__":
    test_integration_suite()
    print()
    print("=" * 60)
    print("ALL BACKEND & INTEGRATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
