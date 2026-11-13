"""Reads the EXISTING ESP32 hub (ESP-NOW prototype) over Wi-Fi and forwards new readings to our server.
No firmware change needed. The laptop/Pi must be on the same Wi-Fi as the hub.
The hub prints its IP in the Serial Monitor at start-up ("Hub IP Address").

  python receiver/hub_poller.py --hub http://192.168.1.50
"""
import argparse, json, time, urllib.request
import os

# If the server was started with IIAAS_KEY set, send it along.
HEADERS = {"Content-Type": "application/json", **({"X-API-Key": os.environ["IIAAS_KEY"]} if os.environ.get("IIAAS_KEY") else {})}

ap = argparse.ArgumentParser()
ap.add_argument("--hub", required=True, help="hub address, e.g. http://192.168.1.50")
ap.add_argument("--url", default="http://localhost:8000/api/ingest")
ap.add_argument("--every", type=float, default=5)
a = ap.parse_args()


def get(path):
    return json.load(urllib.request.urlopen(a.hub.rstrip("/") + path, timeout=5))


def post(p):
    req = urllib.request.Request(a.url, json.dumps(p).encode(), HEADERS)
    urllib.request.urlopen(req, timeout=5)


last = {1: -1, 2: -1}  # newest hub timestamp (ms since hub boot) already sent, per node
while True:
    try:
        uptime = get("/api/status")["uptime"]
        data, now = get("/api/data"), time.time()
        for n in (1, 2):
            entries = data.get(f"log_n{n}", [])
            if entries and entries[-1]["timestamp"] < last[n]:
                last[n] = -1  # hub restarted, its clock started again
            for e in entries:
                if e["timestamp"] > last[n]:
                    p = dict(e, node=f"ESP32_{n}", source="hub",
                             ts=now - (uptime - e["timestamp"]) / 1000)  # real time of that reading
                    post(p)
                    last[n] = e["timestamp"]
    except Exception as ex:
        print("poll failed:", ex)
    time.sleep(a.every)
