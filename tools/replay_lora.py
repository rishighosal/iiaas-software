"""Test the LoRa path WITHOUT the Dev Kit. Replays Dev Kit output lines from a text file through the same
parser as receiver/serial_receiver.py and posts them to the server.
The packets in tools/sample_lora_log.txt were copied from the hardware team's serial monitor screenshot.
Readings are labelled source=sim, so the dashboard shows "Simulated data" (this is not live hardware).

  python tools/replay_lora.py
  python tools/replay_lora.py --file my_dev_kit_log.txt --every 2
"""
import argparse, binascii, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from receiver.serial_receiver import parse_payload

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=str(Path(__file__).with_name("sample_lora_log.txt")))
ap.add_argument("--url", default="http://localhost:8000/api/ingest")
ap.add_argument("--every", type=float, default=3, help="seconds between packets")
ap.add_argument("--loops", type=int, default=0, help="0 = repeat forever")
a = ap.parse_args()

lines = Path(a.file).read_text().splitlines()
n = 0
while a.loops == 0 or n < a.loops:
    n += 1
    rssi = None
    for line in lines:
        m = re.search(r"RSSI:(-?\d+)", line)
        if m:
            rssi = float(m.group(1))
        m = re.search(r'RX "([0-9A-Fa-f]+)"', line)
        if not m:
            continue
        try:
            p = parse_payload(binascii.unhexlify(m.group(1)).decode())
        except Exception as e:
            print("skipped:", e)
            continue
        p["rssi"], p["source"] = rssi, "sim"
        req = urllib.request.Request(a.url, json.dumps(p).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        print(f"replayed {p['node']}  rssi={rssi}  soil%={p.get('soil_percent')}  relay={p.get('relay')}")
        time.sleep(a.every)
