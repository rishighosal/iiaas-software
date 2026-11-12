# IIAAS software v1

Runs on the Raspberry Pi (or any laptop). Works offline, no cloud account needed.

## Run
```
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000                  # server + dashboard -> http://<pi-ip>:8000
python tools/simulator.py                                         # FAKE data, development only
python receiver/hub_poller.py --hub http://<hub-ip>               # REAL data from the existing ESP32 hub (ESP-NOW prototype)
python receiver/serial_receiver.py --port /dev/ttyACM0 --init     # REAL data from the Wio-E5 Dev Kit (LoRa, future)
```
Use only ONE data source at a time (simulator, hub poller or serial receiver). The dashboard shows "Simulated data" when fake readings are present.

## Packets the server accepts (POST /api/ingest)
1. Existing hub JSON
   `{"node":"ESP32_1","temperature":..,"humidity":..,"soil_percent":..,"water_level_raw":..,"mq135_raw":..,"eco2_ppm":..,"relay":..}`
   `{"node":"ESP32_2","temperature":..,"moisture":..,"ph":..,"nitrogen":..,"phosphorus":..,"potassium":..}`
2. Compact LoRa JSON
   `{"id":1,"seq":105,"temp":..,"hum":..,"soil":..,"water":..,"mq135":..}`
   `{"id":2,"seq":106,"soil":..,"soil_temp":..,"ph":..,"n":..,"p":..,"k":..}`

Missing fields are stored as empty. Extra keys are ignored.

## Other endpoints
- `GET /api/latest`: Most recent telemetry per node + server timestamp.
- `GET /api/insights`: Rule-based agronomic recommendations and anomaly warnings.
- `GET /api/history?node=1&hours=24&limit=500`: Historical readings (supports `node`, `hours`, `since`, and `limit`).
- `GET /api/pump-events?limit=50`: Pump relay state transitions (ON/OFF) with timestamps and duration.
- `GET /api/alerts?active=1`: Alert logs (active=1 filters unacknowledged alerts from last 30 min).
- `POST /api/alerts/{id}/ack`: Acknowledge and dismiss an alert.
- `GET /api/export.csv`: Download all readings as CSV.
- `GET /manifest.json`, `GET /sw.js`: PWA web manifest and offline service worker.

## Software-Only Demonstration Mode
Run simulated scenarios without physical hardware using `tools/simulator.py`:
```bash
python tools/simulator.py --scenario normal          # Default realistic drift
python tools/simulator.py --scenario low-moisture    # Low soil moisture (<40%), triggers pump ON
python tools/simulator.py --scenario high-temp       # High temperature (>38°C), heat stress alert
python tools/simulator.py --scenario abnormal-ph     # Extreme pH (4.8 or 8.4) conditioning warning
python tools/simulator.py --scenario pump-cycle      # Rapid relay transitions for pump history demo
python tools/simulator.py --scenario critical        # Combo crisis (low moisture + heat + acid soil)
```

## Documentation
- [docs/architecture.md](docs/architecture.md): Architecture diagram distinguishing implemented vs. planned paths.
- [docs/user-manual.md](docs/user-manual.md): Operator guide for field technicians and farmers.
- [docs/demo-script.md](docs/demo-script.md): Step-by-step 15-minute presentation walkthrough.
- [docs/test-plan.md](docs/test-plan.md): Comprehensive verification checklist (hardware, API, UI, PWA).
- [docs/proposal-pitch-corrections.md](docs/proposal-pitch-corrections.md): Factual qualifications based strictly on code.

## Still to confirm with the hardware team
- LoRa settings (frequency, SF, bandwidth) in receiver/serial_receiver.py must match the transmitter.
- Final packet keys and units (especially N, P, K). Fertilizer limits in app/main.py (CFG) are placeholders.
- The Dev Kit's USB port and baud rate (default /dev/ttyACM0, 9600).

## Hub poller notes
- The hub prints its IP in the Serial Monitor at start-up. The computer running this must be on the same Wi-Fi.
- It reads the hub's /api/status and /api/data, sends only new readings, and rebuilds each reading's real time from the hub's uptime clock.
- It works with the original hub code. If the revised hub code changed these endpoints, send us the new code.
