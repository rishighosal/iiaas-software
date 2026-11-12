# IIAAS Field Monitor — Test Plan

**Version:** 1.0
**Branch:** `feat/dashboard-alerts`
**Coverage areas:** Backend unit logic, API integration, UI functionality, alert system, mobile, PWA, offline behaviour.

---

## 1. Test Environment Setup

```bash
cd iiaas-software-main
pip install -r requirements.txt
pip install -r requirements-dev.txt    # adds pytest

# Terminal A: server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal B: simulator
python tools/simulator.py --every 2

# Terminal C: test runner
pytest tests/
```

---

## 2. Unit Tests (Automated — `tests/test_core.py`)

Run with: `pytest tests/test_core.py -v`

> **Note:** Requires `pip install pytest`. Python 3.14 on this machine did not have pytest pre-installed; install it first.

| Test | Expected Result | Status |
|------|-----------------|--------|
| `test_hub_format_node1` | Normalize ESP32_1 hub JSON → node=1, correct field mapping | Should PASS |
| `test_hub_format_node2` | Normalize ESP32_2 hub JSON → node=2, seq from count field | Should PASS |
| `test_compact_lora_format` | Normalize id=1/id=2 LoRa JSON → correct field mapping | Should PASS |
| `test_unknown_node_rejected` | id=9 raises ValueError | Should PASS |
| `test_bad_values_become_none` | NaN/non-numeric → None in output dict | Should PASS |
| `test_normal_readings_ok` | No anomaly on stable readings | Should PASS |
| `test_stuck_sensor_found` | 30 identical readings → "stuck" in output | Should PASS |
| `test_few_identical_readings_not_stuck` | 5 identical readings → no anomaly | Should PASS |
| `test_sudden_jump_found` | 50→51→88 moisture → "jumped" in output | Should PASS |
| `test_small_change_not_a_jump` | 50→60 moisture → no anomaly | Should PASS |
| `test_out_of_range_found` | moisture=140 → "out of range" in output | Should PASS |

---

## 3. Integration Tests (Automated — `tests/test_integration.py`)

Run with: `python tests/test_integration.py`

| Test | Expected Result |
|------|-----------------|
| Pump event detection from relay transitions | 2 events (1 ON, 1 OFF) with correct timestamps |
| OFF event duration calculation | duration_s ≈ 120 s |
| `/api/history` returns all rows | 5 rows inserted, 5 returned |
| `/api/history?hours=0.01` time filter | Only rows from last 36 s returned (0 for old test data) |

---

## 4. API Endpoint Tests (Manual — Server Running)

### 4.1 `/api/latest`

```bash
curl http://localhost:8000/api/latest
```

| Check | Expected |
|-------|----------|
| Returns `{"now": <float>, "nodes": {"1": {...}, "2": {...}}}` | ✓ |
| `nodes["1"].data` contains `air_temp`, `humidity`, `soil_moisture`, `relay` | ✓ |
| `nodes["2"].data` contains `ph`, `n`, `p`, `k`, `soil_temp` | ✓ |
| `source` field is `"sim"` when simulator is running | ✓ |

### 4.2 `/api/insights`

```bash
curl http://localhost:8000/api/insights
```

| Check | Expected |
|-------|----------|
| Returns array of `{level, msg}` objects | ✓ |
| `level` is one of: `"ok"`, `"bad"`, `"warn"`, `"info"` | ✓ |
| When soil < 40%: `{"level":"bad","msg":"...Irrigate..."}` | ✓ |
| When all in range: `[{"level":"ok","msg":"All readings..."}]` | ✓ |

### 4.3 `/api/history`

```bash
curl "http://localhost:8000/api/history?node=1&limit=10"
curl "http://localhost:8000/api/history?hours=1"
curl "http://localhost:8000/api/history?limit=5"
```

| Check | Expected |
|-------|----------|
| Returned rows are in ascending time order | ✓ |
| `?node=1` returns only node=1 rows | ✓ |
| `?hours=1` returns only rows from last 1 hour | ✓ |
| `?limit=5` returns at most 5 rows | ✓ |
| Row has `ts, node, seq, source` plus sensor fields | ✓ |
| Existing endpoint still works without new params | ✓ |

### 4.4 `/api/pump-events`

```bash
curl "http://localhost:8000/api/pump-events?limit=20"
```

| Check | Expected |
|-------|----------|
| Returns array (may be empty if no transitions yet) | ✓ |
| Each event has `ts, event ("on"/"off"), soil_moisture, duration_s` | ✓ |
| OFF events have `duration_s` populated | ✓ |
| ON events have `duration_s: null` | ✓ |
| Most recent events returned first | ✓ |
| Does not change any database schema | ✓ |

### 4.5 `/api/alerts`

```bash
curl "http://localhost:8000/api/alerts?limit=10"
curl "http://localhost:8000/api/alerts?active=1"
```

| Check | Expected |
|-------|----------|
| Returns array of alert objects | ✓ |
| `?active=1` returns only unacknowledged alerts from last 30 min | ✓ |
| Each alert has `id, ts, node, level, msg, channel, sent, acked` | ✓ |

### 4.6 `/api/alerts/{id}/ack`

```bash
# Get an alert ID first, then:
curl -X POST http://localhost:8000/api/alerts/1/ack
```

| Check | Expected |
|-------|----------|
| Returns `{"ok": true}` | ✓ |
| Subsequent `GET /api/alerts?active=1` does not include that alert | ✓ |
| Non-existent ID returns HTTP 404 | ✓ |

### 4.7 `/api/ingest` (existing, must not break)

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"node":"ESP32_1","temperature":30,"humidity":65,"soil_percent":55,"relay":false}'
```

| Check | Expected |
|-------|----------|
| Returns `{"ok": true, "node": 1}` | ✓ |
| `GET /api/latest` immediately shows updated values | ✓ |
| Invalid packet returns HTTP 422 | ✓ |

### 4.8 `/api/export.csv`

```bash
curl http://localhost:8000/api/export.csv -o test.csv
```

| Check | Expected |
|-------|----------|
| File starts with correct CSV header | ✓ |
| All known columns present: `ts, node, seq, source, air_temp, humidity, ...` | ✓ |
| Data rows have correct number of fields | ✓ |

---

## 5. Frontend / Dashboard Tests (Manual — Browser)

### 5.1 Initial Load

| Check | Expected |
|-------|----------|
| Dashboard loads at `http://localhost:8000` | ✓ |
| Status badge shows "Simulated data" (yellow dot) when simulator running | ✓ |
| All three condition cards populate within 5 seconds | ✓ |
| No JavaScript errors in browser console | ✓ |

### 5.2 Dashboard Tab

| Check | Expected |
|-------|----------|
| Node 1 card shows air_temp, humidity, soil_moisture, water_raw, relay | ✓ |
| Node 2 card shows soil_temp, soil_moisture, ph, n, p, k | ✓ |
| Node age badge goes green/yellow/red based on data freshness | ✓ |
| Recommendations list updates every 5 seconds | ✓ |
| Soil moisture chart draws lines for both nodes | ✓ |
| Red dashed threshold line at 40% visible in chart | ✓ |
| Chart time filter "1 Hour" re-fetches and redraws | ✓ |
| Chart time filter "24 Hours" re-fetches and redraws | ✓ |
| Chart time filter "All" shows all available data | ✓ |
| Pump history populates when relay transitions exist | ✓ |
| Pump ON event shows "ON" badge + timestamp + soil moisture | ✓ |
| Pump OFF event shows "OFF" badge + duration | ✓ |

### 5.3 Active Alert Banner

| Check | Expected |
|-------|----------|
| Banner appears when insights contain "bad" or "warn" level | ✓ |
| Banner hidden when all insights are "ok" | ✓ |
| Mute button toggles audio on/off | ✓ |
| Dismiss button hides banner for current set of alerts | ✓ |
| Banner reappears if a **new** alert type appears after dismissal | ✓ |
| Audio chime plays only once per new unique alert (not every 5 s) | ✓ |
| Alert count badge appears on "Alerts" nav tab when active alerts exist | ✓ |

### 5.4 Alerts Tab

| Check | Expected |
|-------|----------|
| Clicking "🔔 Alerts" switches to alerts page | ✓ |
| All filter shows all alerts in database | ✓ |
| Active filter shows only unacknowledged alerts <30 min old | ✓ |
| Dismissed filter shows only acknowledged alerts | ✓ |
| Alert count badge updates correctly | ✓ |
| Dismiss button on a row calls POST /api/alerts/{id}/ack | ✓ |
| Row fades after dismissal | ✓ |
| "Refresh" button reloads alerts list | ✓ |

---

## 6. Responsive / Mobile Tests

Resize the browser window or use Chrome DevTools mobile emulation (F12 → Toggle device toolbar).

| Screen Size | Check | Expected |
|-------------|-------|----------|
| 360×640 (phone) | Nav bar fits, all tabs accessible | ✓ |
| 360×640 | Brand name may hide, icons remain | ✓ |
| 360×640 | Cards stack vertically | ✓ |
| 360×640 | Chart readable, 180px height | ✓ |
| 360×640 | Filter buttons wrap but remain tappable | ✓ |
| 768×1024 (tablet) | 2-column grid active | ✓ |
| 1280×800 (desktop) | 3-column grid in top row | ✓ |
| All sizes | No horizontal scroll | ✓ |
| All sizes | Tap targets ≥ 44×44px | ✓ |

---

## 7. PWA Tests

### 7.1 Manifest

```bash
curl http://localhost:8000/manifest.json
```

| Check | Expected |
|-------|----------|
| Returns valid JSON | ✓ |
| `name`, `short_name`, `start_url`, `display`, `theme_color`, `icons` present | ✓ |
| Icons array lists 192px and 512px entries | ✓ |

### 7.2 Service Worker

Open browser DevTools → Application → Service Workers.

| Check | Expected |
|-------|----------|
| `/sw.js` loads and registers | ✓ |
| Status shows "activated and running" | ✓ |
| Cache named `iiaas-v1` appears in Cache Storage | ✓ |
| `/` and `/manifest.json` are in cache | ✓ |

### 7.3 Offline Shell

1. With the app loaded, go to DevTools → Network → check "Offline".
2. Reload the page.

| Check | Expected |
|-------|----------|
| Dashboard HTML still loads from cache | ✓ |
| API calls fail gracefully (status badge shows "Cannot reach server") | ✓ |
| No white screen or crash | ✓ |

---

## 8. Alert Worker Tests (requires running worker)

```bash
python tools/alert_worker.py
```

| Check | Expected |
|-------|----------|
| Worker starts and prints "alert worker running; Telegram OFF (log only)" | ✓ |
| When `/api/insights` returns a "bad" alert, worker logs it to `alerts` table | ✓ |
| Same alert does not re-fire within the cooldown period (1800s default) | ✓ |
| Alert appears in `GET /api/alerts` within 20 seconds | ✓ |

---

## 9. Features Requiring Real Hardware or External Config

These cannot be fully tested without additional setup:

| Feature | Requirement |
|---------|-------------|
| Hub poller receiving real data | ESP32 hub on the same Wi-Fi; run `python receiver/hub_poller.py --hub http://<hub-ip>` |
| LoRa serial receiver | Wio-E5 Dev Kit + confirmed frequency/SF/BW from hardware team |
| Telegram alerts | `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` environment variables |
| Gmail alerts | `GMAIL_USER` and `GMAIL_APP_PASSWORD` environment variables |
| PWA install prompt | Must be served over HTTPS or localhost; real device testing |
| Pump relay events (real) | Physical pump connected to Node 1 relay |
| NPK readings (real) | Hardware team to confirm sensor units and calibration |

---

## 10. Known Limitations

| Limitation | Notes |
|-----------|-------|
| No HTTPS in default setup | PWA install on Android/iOS requires HTTPS outside of localhost; configure nginx + Let's Encrypt on the Pi for production |
| SQLite not concurrent | SQLite has write locking; a single writer (ingest) + multiple readers is fine for the expected load |
| `int \| None` type hints | Requires Python 3.10+; documented in requirements |
| Audio blocked on first load | Web Audio API requires a user gesture; documented in user manual |
| Pump history empty on fresh DB | Only populated after relay state changes occur |

