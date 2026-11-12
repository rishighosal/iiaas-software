"""Runs on the laptop/Pi that has the Wio-E5 Dev Kit on USB. Reads LoRa packets and sends them to the API.
The hub sends CSV text such as  N1,210535,27.60,75.00,4095,0,4095,1,243,0.196,400  (JSON also works).
Windows: --port COM5 (close the Arduino Serial Monitor first, only one program can use the port).
Unsent packets are kept in unsent.jsonl."""
import argparse, binascii, json, re, time, urllib.request

# LoRa settings of the hub's Wio-E5 Mini, from its start-up log: 866 MHz, SF12, 125 kHz.
INIT = ["AT", "AT+MODE=TEST", "AT+TEST=RFCFG,866,SF12,125,12,15,14,ON,OFF,OFF", "AT+TEST=RXLRPKT"]

# CSV order after "N1,<hub ms>": read from real packets (matches the hub's JSON for Node 1).
N1_FIELDS = ["temperature", "humidity", "soil_raw", "soil_percent", "water_level_raw",
             "relay", "mq135_raw", "mq135_voltage", "eco2_ppm"]
# ASSUMED, not yet seen on the air: same order as the hub's JSON for Node 2. Confirm with a real N2 line.
N2_FIELDS = ["temperature", "moisture", "ph", "nitrogen", "phosphorus", "potassium"]


def parse_payload(text):
    """LoRa text -> the dict that /api/ingest accepts. Raises ValueError for anything unknown."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    parts = text.split(",")
    names = {"N1": N1_FIELDS, "N2": N2_FIELDS}.get(parts[0])
    if names is None or len(parts) != len(names) + 2:
        raise ValueError("unknown packet: " + text[:60])
    p = {"node": "ESP32_" + parts[0][1], "hub_ms": float(parts[1])}  # hub_ms is ignored by the server
    for k, v in zip(names, parts[2:]):
        p[k] = float(v)
    if "relay" in p:
        p["relay"] = bool(p["relay"])
    return p


def main():
    import serial
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--url", default="http://localhost:8000/api/ingest")
    ap.add_argument("--init", action="store_true", help="send the receive-mode AT commands first")
    a = ap.parse_args()

    def post(p):
        try:
            req = urllib.request.Request(a.url, json.dumps(p).encode(), {"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print("post failed, saved:", type(e).__name__)
            open("unsent.jsonl", "a").write(json.dumps(p) + "\n")

    print("Node 2 CSV field order is ASSUMED until a real N2 packet is confirmed.")
    rssi = None
    with serial.Serial(a.port, a.baud, timeout=1) as s:
        if a.init:
            for c in INIT:
                s.write((c + "\r\n").encode()); time.sleep(0.5)
        while True:
            line = s.readline().decode(errors="ignore").strip()
            if not line:
                continue
            print(line)
            m = re.search(r"RSSI:(-?\d+)", line)
            if m:
                rssi = float(m.group(1))
            m = re.search(r'RX "([0-9A-Fa-f]+)"', line)
            if m:
                try:
                    p = parse_payload(binascii.unhexlify(m.group(1)).decode())
                except Exception as e:
                    print("skipped:", e); continue
                p["rssi"], p["source"] = rssi, "lora"
                post(p)


if __name__ == "__main__":
    main()
