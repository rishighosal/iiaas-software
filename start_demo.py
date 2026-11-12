"""One command to start the demo: the server + one data source (+ alerts), then open the dashboard.

  python start_demo.py --source replay                      real LoRa packets replayed (no hardware needed)
  python start_demo.py --source sim                         simulator
  python start_demo.py --source hub --hub http://10.66.98.65   live from the ESP32 hub over Wi-Fi
  python start_demo.py --source lora --port COM5            live from the Wio-E5 Dev Kit on USB
Add --alerts to also run the alert worker, --fresh to delete the old database first.
Ctrl+C stops everything.
"""
import argparse, os, socket, subprocess, sys, time, urllib.request, webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=["replay", "sim", "hub", "lora", "none"], default="replay")
ap.add_argument("--hub", help="hub address, for example http://10.66.98.65")
ap.add_argument("--port", default="COM5", help="Dev Kit serial port (for --source lora)")
ap.add_argument("--web-port", type=int, default=8000)
ap.add_argument("--alerts", action="store_true", help="also run tools/alert_worker.py")
ap.add_argument("--fresh", action="store_true", help="delete iiaas.db first (no old readings)")
ap.add_argument("--no-browser", action="store_true")
a = ap.parse_args()

if a.source == "hub" and not a.hub:
    sys.exit("--source hub needs --hub http://<hub-ip>")
if a.fresh:
    try:
        (ROOT / "iiaas.db").unlink(missing_ok=True)
    except PermissionError:
        sys.exit("Cannot delete iiaas.db: an old server is still running. Close it and try again.")

base = f"http://localhost:{a.web_port}"
ingest = base + "/api/ingest"
sources = {
    "replay": ["tools/replay_lora.py", "--url", ingest],
    "sim": ["tools/simulator.py", "--url", ingest],
    "hub": ["receiver/hub_poller.py", "--hub", a.hub or "", "--url", ingest],
    "lora": ["receiver/serial_receiver.py", "--port", a.port, "--url", ingest],
}
env = {**os.environ, "IIAAS_API": base}  # the alert worker reads this
procs = []


def start(name, args):
    procs.append((name, subprocess.Popen([PY, *args], cwd=ROOT, env=env)))


def stop_all():
    for _, p in procs:
        if p.poll() is None:
            p.terminate()
    for _, p in procs:
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


start("server", ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(a.web_port),
                 "--log-level", "warning"])
for _ in range(40):
    try:
        urllib.request.urlopen(base + "/api/latest", timeout=1)
        break
    except Exception:
        time.sleep(0.5)
else:
    stop_all()
    sys.exit("The server did not start. Is another program using port %d?" % a.web_port)

if a.source != "none":
    start(a.source, sources[a.source])
if a.alerts:
    start("alerts", ["tools/alert_worker.py"])

ip = lan_ip()
print(f"\nIIAAS is running.  Source: {a.source}" + ("  +alerts" if a.alerts else ""))
print(f"  This computer : {base}")
if ip:
    print(f"  Phone (same Wi-Fi): http://{ip}:{a.web_port}")
print("  Press Ctrl+C to stop everything.\n")
if not a.no_browser:
    webbrowser.open(base)

try:
    while procs:
        time.sleep(2)
        for item in list(procs):
            name, p = item
            if p.poll() is not None:
                print(f"!! {name} stopped (exit code {p.returncode}). See the messages above.")
                procs.remove(item)
                if name == "server":
                    procs.clear()
except KeyboardInterrupt:
    pass
finally:
    stop_all()
    print("Stopped.")
