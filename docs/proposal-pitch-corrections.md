# IIAAS Proposal / Pitch — Corrections and Clarifications

**Purpose:** This document records factual corrections and important clarifications about the IIAAS system that should be reflected in any presentation, proposal, or pitch.

**Scope:** This document was written based on inspection of the actual source code and README only. It does not comment on any external proposal documents that have not been reviewed.

---

## 1. What Is Correctly Stated in the Repository

The following claims are confirmed by the source code:

| Claim | Verified Source |
|-------|----------------|
| System runs fully offline on a Raspberry Pi | `README.md`, `app/main.py` — SQLite, no cloud dependencies |
| Works with the existing ESP32 hub without firmware changes | `receiver/hub_poller.py` — reads `/api/status` and `/api/data` endpoints |
| Supports two data paths: Wi-Fi hub and LoRa serial | `receiver/hub_poller.py`, `receiver/serial_receiver.py` |
| Node 1 measures air temp, humidity, soil moisture, water level, gas (MQ-135), eCO₂, pump relay | `app/main.py normalize()`, `tools/simulator.py` |
| Node 2 measures soil temp, soil moisture, pH, N, P, K | `app/main.py normalize()`, `tools/simulator.py` |
| Soil moisture threshold of 40% matches Node 1 firmware | Comment in `app/main.py`: `# moist_low=40 matches the Node 1 firmware` |
| Alert system supports Telegram and Gmail | `tools/alert_worker.py` |
| Dashboard auto-refreshes | `static/index.html` — `setInterval(tick, 5000)` |

---

## 2. Claims That Require Qualification

### 2.1 LoRa / Wio-E5 Integration

**Status:** Code implemented; not yet validated with real hardware.

The serial receiver (`receiver/serial_receiver.py`) is written and handles the AT command protocol for the Wio-E5 Dev Kit. However:

- LoRa settings (frequency, spreading factor, bandwidth) are hardcoded as defaults (`866 MHz, SF7, 125 kHz`).
- These **must be confirmed with the hardware team** to match the transmitter settings.
- Until this is confirmed, LoRa reception cannot be tested end-to-end.

**Correction to avoid:** Do not claim LoRa is fully operational. Correct phrasing: *"The LoRa receiver is code-complete and pending hardware configuration confirmation."*

### 2.2 NPK Sensor Readings

**Status:** NPK values are stored and displayed, but thresholds are explicitly marked as placeholders.

From `app/main.py`:
```python
# pH/NPK values are PLACEHOLDERS (crop and sensor units not confirmed).
CFG = dict(..., n_low=50, p_low=20, k_low=100)
```

The insights engine already warns: *"Confirm sensor units and crop targets before advising fertilizer."*

**Correction to avoid:** Do not claim the system gives accurate fertilizer recommendations. Correct phrasing: *"The system tracks NPK sensor readings. Agronomic thresholds will be calibrated once sensor units are confirmed with the hardware team."*

### 2.3 pH Sensor

**Status:** pH is read and plausibility-checked (0–14 range), but sensor calibration is not confirmed.

The code checks `if not 0 <= ph <= 14` as a sanity check, but does not validate sensor model or calibration. README notes: *"Final packet keys and units (especially N, P, K). Fertilizer limits in app/main.py (CFG) are placeholders."*

### 2.4 eCO₂ Reading

**Status:** Stored and displayed, but labelled as an estimate.

The field is called `eco2_ppm` (estimated CO₂). The MQ-135 sensor provides a raw ADC value that is converted to an estimated ppm reading. This is an approximation, not a calibrated measurement.

**Correct labelling:** "eCO₂ estimate" — as already shown in the dashboard.

---

## 3. What the Dashboard Does NOT Include (By Design)

These features are **not present** and should not be described as implemented:

| Feature | Reality |
|---------|---------|
| External weather forecast | Not integrated. The dashboard shows only on-field sensor measurements. |
| Cloud connectivity | Explicitly designed to be offline-only. |
| Machine learning / predictive analytics | Not present. All insights are rule-based thresholds. |
| Automated pump control from the software | The pump relay is controlled by Node 1 firmware based on its own thresholds. The software **reads** the relay state; it does not send commands to the hardware. |
| Multi-farm / multi-site support | Single deployment, single SQLite database, two nodes only. |

---

## 4. Data That Is Simulated vs. Real

The system clearly distinguishes simulated data:

- The status bar shows 🟡 "Simulated data" when `source = "sim"`.
- The simulator (`tools/simulator.py`) is for development/demo only and is explicitly documented as such.

**Correction to avoid:** Do not present simulator screenshots as real field data without disclosure.

---

## 5. Packet Format Dependencies

The hub poller depends on the existing ESP32 hub serving two specific endpoints:
- `GET /api/status` → must return `{"uptime": <ms>}`
- `GET /api/data` → must return `{"log_n1": [...], "log_n2": [...]}`

From `README.md`: *"It works with the original hub code. If the revised hub code changed these endpoints, send us the new code."*

If the hub firmware has been updated, the poller may need adjustment.

---

## 6. Summary Table

| Category | Fully Implemented | Partially / Pending | Not Implemented |
|----------|:-----------------:|:-------------------:|:---------------:|
| ESP-NOW hub data path | ✅ | | |
| LoRa data path | | ⚠ Pending HW config | |
| All Node 1 sensors | ✅ | | |
| All Node 2 sensors (reading) | ✅ | | |
| NPK thresholds (calibrated) | | ⚠ Placeholders | |
| pH calibration | | ⚠ Not confirmed | |
| Dashboard UI | ✅ | | |
| Alerts (log + Telegram/Gmail) | ✅ | | |
| PWA installable | ✅ | | |
| External weather API | | | ❌ |
| Software pump control | | | ❌ (read-only) |
| ML/predictive analytics | | | ❌ |
| Cloud connectivity | | | ❌ (by design) |

