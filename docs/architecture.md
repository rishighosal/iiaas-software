# IIAAS Field Monitor — Architecture

## System Overview

IIAAS (Intelligent Irrigation & Automation System) runs on a Raspberry Pi or laptop. It has three major layers: **hardware sensor nodes**, the **ingestion and processing backend**, and the **browser-based dashboard**.

---

## Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                     HARDWARE LAYER                                    ║
║                                                                        ║
║  ┌─────────────────────┐       ┌─────────────────────┐               ║
║  │  Node 1 (ESP32)      │       │  Node 2 (ESP32)      │               ║
║  │  Air & Irrigation    │       │  Soil Chemistry       │               ║
║  │  · Air temperature   │       │  · Soil temperature   │               ║
║  │  · Humidity          │       │  · Soil moisture      │               ║
║  │  · Soil moisture     │       │  · pH                 │               ║
║  │  · Water level (ADC) │       │  · Nitrogen (ADC)     │               ║
║  │  · MQ-135 gas (ADC)  │       │  · Phosphorus (ADC)   │               ║
║  │  · eCO₂ (est.)       │       │  · Potassium (ADC)    │               ║
║  │  · Pump relay state  │       └──────────┬────────────┘               ║
║  └──────────┬───────────┘                  │                            ║
║             │  ESP-NOW radio               │  ESP-NOW radio             ║
║             └──────────────┐  ┌───────────┘                            ║
║                            ▼  ▼                                        ║
║               ┌────────────────────┐                                   ║
║               │  ESP32 Hub          │  ← IMPLEMENTED                   ║
║               │  Aggregates ESP-NOW │                                   ║
║               │  Serves /api/status │                                   ║
║               │  Serves /api/data   │                                   ║
║               └─────────┬──────────┘                                   ║
║                          │ Wi-Fi HTTP (same LAN)                        ║
╚══════════════════════════╪═════════════════════════════════════════════╝
                           │
╔══════════════════════════╪═════════════════════════════════════════════╗
║               DATA INGESTION LAYER (Raspberry Pi / Laptop)             ║
║                                                                         ║
║  ┌────────────────────┐  │  ┌──────────────────┐  ┌──────────────────┐║
║  │ receiver/           │  │  │ receiver/         │  │ tools/           │║
║  │ hub_poller.py       │◄─┘  │ serial_receiver.py│  │ simulator.py     │║
║  │                     │     │                   │  │                  │║
║  │ IMPLEMENTED ✓       │     │ IMPLEMENTED ✓     │  │ Dev/demo only ✓  │║
║  │ Polls hub every 5s  │     │ LoRa USB serial   │  │ Sends fake data  │║
║  │ Reconstructs real   │     │ AT commands, RSSI  │  │ source="sim"     │║
║  │ timestamps from hub │     │ Hex→JSON decode    │  │                  │║
║  │ uptime              │     │ ⚠ LoRa settings   │  │                  │║
║  └──────────┬──────────┘     │ not yet confirmed  │  └──────┬───────────┘║
║             │                └────────┬───────────┘         │           ║
║             │                         │  ⚠ PENDING          │           ║
║             └──────────┬──────────────┘                     │           ║
║                        ▼ POST /api/ingest ◄──────────────────┘           ║
╚════════════════════════╪════════════════════════════════════════════════╝
                         │
╔════════════════════════╪════════════════════════════════════════════════╗
║               BACKEND LAYER (FastAPI / Python)                          ║
║                                                                          ║
║               ┌─────────────────────────────────────┐                   ║
║               │  app/main.py  (FastAPI app)           │                  ║
║               │                                       │                  ║
║               │  normalize()   Hub JSON + LoRa JSON   │                  ║
║               │  /api/ingest   Write to SQLite         │                  ║
║               │  /api/latest   Most recent per node    │                  ║
║               │  /api/insights Rule-based advice       │                  ║
║               │  /api/history  ?node&limit&hours&since │ ← NEW          ║
║               │  /api/pump-events  Relay transitions   │ ← NEW          ║
║               │  /api/export.csv   CSV download        │                  ║
║               └───────────┬─────────────────┬─────────┘                  ║
║                           │                 │                             ║
║               ┌───────────▼──────┐  ┌───────▼─────────┐                 ║
║               │  app/anomaly.py   │  │  app/alerts.py   │                ║
║               │  Stuck sensor     │  │  /api/alerts     │                ║
║               │  Sudden jump      │  │  /api/alerts/ack │                ║
║               │  Out-of-range     │  │                  │                ║
║               └──────────────────┘  └──────────────────┘                ║
║                                                                           ║
║               ┌───────────────────────────────────┐                      ║
║               │  SQLite: iiaas.db                  │                      ║
║               │  · readings (id,ts,node,seq,rssi,  │                      ║
║               │             source,data JSON)       │                      ║
║               │  · alerts   (id,ts,node,level,msg, │                      ║
║               │             channel,sent,acked)     │                      ║
║               └───────────────────────────────────┘                      ║
║                                                                           ║
║               ┌───────────────────────────────────┐                      ║
║               │  tools/alert_worker.py             │                      ║
║               │  Polls /api/insights every 20s     │                      ║
║               │  Sends Telegram / Gmail / log-only │                      ║
║               │  Cooldown: 1800s per unique alert  │                      ║
║               └───────────────────────────────────┘                      ║
╚════════════════════════════════════════════════════════════════════════╝
                         │
╔════════════════════════╪════════════════════════════════════════════════╗
║               FRONTEND LAYER (Browser PWA)                               ║
║                                                                           ║
║               static/index.html   ← Full SPA dashboard                  ║
║                                                                           ║
║   Dashboard Tab:                      Alerts Tab:                        ║
║   · Field Conditions cards            · Alert log table                  ║
║   · Air / Soil / Irrigation metrics   · Active / All / Dismissed filter  ║
║   · Recommendations (from insights)   · Acknowledge / dismiss button     ║
║   · Soil moisture chart               · Load more pagination             ║
║     ↳ 1 Hour / 24 Hours / All filter                                     ║
║   · Pump ON/OFF history timeline                                          ║
║   · Active alert banner + audio alert                                    ║
║                                                                           ║
║   static/manifest.json  → PWA installable on phone                       ║
║   static/sw.js          → Service worker, offline shell cache            ║
║   static/icons/         → App icons 192px + 512px                       ║
╚════════════════════════════════════════════════════════════════════════╝
```

---

## Data Flow Summary

```
Sensor Node → [ESP-NOW] → Hub → [Wi-Fi HTTP] → hub_poller.py
                                                     ↓
                              POST /api/ingest (normalize)
                                                     ↓
                                             SQLite readings
                                                     ↓
                              GET /api/latest / /api/history / /api/pump-events
                                                     ↓
                                       Browser Dashboard (every 5 s)
```

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| ESP32 Hub (ESP-NOW) | ✅ Hardware exists | Existing firmware, hub poller works |
| Hub poller | ✅ Implemented | `receiver/hub_poller.py` |
| LoRa serial receiver | ✅ Implemented | `receiver/serial_receiver.py` — **LoRa settings not yet confirmed with hardware team** |
| Simulator | ✅ Implemented | Development/demo only |
| `/api/ingest` | ✅ Implemented | Dual-format JSON normalization |
| `/api/latest` | ✅ Implemented | Most recent reading per node |
| `/api/insights` | ✅ Implemented | Rule-based recommendations |
| `/api/history` | ✅ Enhanced | Added `hours`/`since` time filter |
| `/api/pump-events` | ✅ New | Relay state-transition detection |
| `/api/export.csv` | ✅ Implemented | Full data download |
| `/api/alerts` + ack | ✅ Implemented | Alert log with dismiss support |
| Alert worker | ✅ Implemented | Telegram + Gmail + log |
| Dashboard UI | ✅ Upgraded | Full responsive SPA |
| Alerts page UI | ✅ New | Filter, dismiss, paginate |
| Chart time filters | ✅ New | 1h / 24h / All |
| Pump history UI | ✅ New | Derived from relay transitions |
| Active alert banner | ✅ New | Sticky banner + Web Audio beep |
| Weather/condition cards | ✅ New | Measured sensor data only |
| Recommendation cards | ✅ New | From existing `/api/insights` |
| PWA support | ✅ New | manifest.json + sw.js + icons |
| Wio-E5 LoRa hardware | ⚠ Pending | Requires hardware team to confirm LoRa settings |
| N/P/K sensor units | ⚠ Pending | Thresholds are placeholders |
| pH sensor calibration | ⚠ Pending | Confirm sensor model and units |

---

## Planned / Not Yet Implemented

- **Wio-E5 Dev Kit**: The serial receiver code exists but LoRa frequency, spreading factor, and bandwidth must be confirmed with the hardware team before it can be used with real sensors.
- **N/P/K units**: Fertilizer limits in `CFG` are clearly marked as placeholders; real thresholds require agronomy input.
- **External weather forecast**: The dashboard displays only on-field sensor measurements. No external weather API is integrated.

