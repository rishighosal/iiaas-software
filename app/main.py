"""IIAAS software v1: ingest -> SQLite -> rules -> dashboard.
Run: uvicorn app.main:app --host 0.0.0.0 --port 8000"""
import csv, io, json, math, sqlite3, time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from app.alerts import router as alerts_router
from app.anomaly import check as anomaly_check

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "iiaas.db"
# moist_low=40 matches the Node 1 firmware. pH/NPK values are PLACEHOLDERS (crop and sensor units not confirmed).
CFG = dict(moist_low=40, moist_high=80, ph_low=5.5, ph_high=7.5, temp_high=38,
           offline_s=120, n_low=50, p_low=20, k_low=100)
app = FastAPI(title="IIAAS")
app.include_router(alerts_router)


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY, ts REAL, node INT, "
              "seq INT, rssi REAL, source TEXT, data TEXT)")
    return c


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def normalize(p):
    """Accepts the existing hub JSON (node:ESP32_1/2) and the compact LoRa JSON (id:1/2)."""
    nid = p.get("id") or {"ESP32_1": 1, "ESP32_2": 2}.get(p.get("node"))
    if nid not in (1, 2):
        raise ValueError("packet needs id 1/2 or node ESP32_1/ESP32_2")
    g = lambda *k: next((num(p[x]) for x in k if x in p and num(p[x]) is not None), None)
    if nid == 1:
        d = dict(air_temp=g("temperature", "temp"), humidity=g("humidity", "hum"),
                 soil_moisture=g("soil_percent", "soil"), water_raw=g("water_level_raw", "water"),
                 mq135_raw=g("mq135_raw", "mq135"), eco2_ppm=g("eco2_ppm"),
                 relay=bool(p["relay"]) if "relay" in p else None)
    else:
        d = dict(soil_temp=g("temperature", "soil_temp"), soil_moisture=g("moisture", "soil"),
                 ph=g("ph"), n=g("nitrogen", "n"), p=g("phosphorus", "p"), k=g("potassium", "k"))
    return int(nid), g("seq", "count"), d


@app.post("/api/ingest")
def ingest(p: dict):
    try:
        node, seq, d = normalize(p)
    except Exception as e:
        raise HTTPException(422, str(e))
    ts = num(p.get("ts"))  # optional: lets the hub poller store the real time of older readings
    if ts is None or ts > time.time() + 5:
        ts = time.time()
    c = db()
    try:
        with c:
            c.execute("INSERT INTO readings(ts,node,seq,rssi,source,data) VALUES(?,?,?,?,?,?)",
                      (ts, node, seq, num(p.get("rssi")), p.get("source", "device"), json.dumps(d)))
    finally:
        c.close()
    return {"ok": True, "node": node}


def latest():
    c = db()
    out = {}
    try:
        for n in (1, 2):
            r = c.execute("SELECT * FROM readings WHERE node=? ORDER BY id DESC LIMIT 1", (n,)).fetchone()
            if r:
                out[n] = dict(ts=r["ts"], seq=r["seq"], rssi=r["rssi"], source=r["source"], data=json.loads(r["data"]))
    finally:
        c.close()
    return out


@app.get("/api/latest")
def api_latest():
    return {"now": time.time(), "nodes": latest()}


@app.get("/api/insights")
def insights():
    l, now, out = latest(), time.time(), []
    add = lambda level, msg: out.append({"level": level, "msg": msg})
    for n in (1, 2):
        r = l.get(n)
        if not r:
            add("warn", f"Node {n}: no data yet."); continue
        age = now - r["ts"]
        if age > CFG["offline_s"]:
            add("bad", f"Node {n} is offline. Last data {int(age)} s ago."); continue
        d = r["data"]; m = d.get("soil_moisture"); t = d.get("air_temp"); ph = d.get("ph")
        if m is not None and m < CFG["moist_low"]:
            add("bad", f"Node {n}: soil moisture {m:.0f}% is below {CFG['moist_low']}%. Irrigate.")
        elif m is not None and m > CFG["moist_high"]:
            add("warn", f"Node {n}: soil moisture {m:.0f}% is high. Pause irrigation.")
        if t is not None and t > CFG["temp_high"]:
            add("warn", f"Node {n}: air temperature {t:.1f} °C. Heat stress risk.")
        if ph is not None:
            if not 0 <= ph <= 14: add("bad", "Node 2: pH reading is out of range. Check the sensor.")
            elif ph < CFG["ph_low"]: add("warn", f"Node 2: soil is acidic (pH {ph:.1f}). Test the soil before liming.")
            elif ph > CFG["ph_high"]: add("warn", f"Node 2: soil is alkaline (pH {ph:.1f}). Test the soil before treating.")
        out.extend(anomaly_check(n, history(n, 200)))
        for k, name in (("n", "Nitrogen"), ("p", "Phosphorus"), ("k", "Potassium")):
            v = d.get(k)
            if v is not None and v < CFG[k + "_low"]:
                add("info", f"Node 2: {name} {v:.0f} is under the placeholder limit {CFG[k + '_low']}. "
                            "Confirm sensor units and crop targets before advising fertilizer.")
    return out or [{"level": "ok", "msg": "All readings are within range."}]


@app.get("/api/history")
def history(node: int | None = None, limit: int = 100, hours: float | None = None, since: float | None = None):
    """Return readings. Optionally filter by node, limit, hours (last N hours), or since (Unix timestamp)."""
    wheres = []
    args = []
    if node is not None:
        wheres.append("node = ?")
        args.append(int(node))
    if hours is not None and hours > 0:
        wheres.append("ts > ?")
        args.append(time.time() - hours * 3600)
    elif since is not None:
        wheres.append("ts > ?")
        args.append(since)
    q = "SELECT * FROM readings"
    if wheres:
        q += " WHERE " + " AND ".join(wheres)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(min(limit, 2000))
    c = db()
    try:
        rows = c.execute(q, args).fetchall()
    finally:
        c.close()
    return [dict(ts=r["ts"], node=r["node"], seq=r["seq"], source=r["source"], **json.loads(r["data"]))
            for r in reversed(rows)]


@app.get("/api/export.csv")
def export_csv():
    rows = history(None, 2000)
    cols = ["ts", "node", "seq", "source", "air_temp", "humidity", "soil_moisture", "water_raw", "mq135_raw",
            "eco2_ppm", "relay", "soil_temp", "ph", "n", "p", "k"]
    buf = io.StringIO(); w = csv.DictWriter(buf, cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=iiaas_readings.csv"})


@app.get("/api/pump-events")
def pump_events(limit: int = 100):
    """
    Derive pump ON/OFF events from Node 1 relay state transitions stored in `readings`.
    Returns a list of events: {ts, event:'on'|'off', soil_moisture, duration_s (for OFF events)}.
    No schema changes — reads from existing `readings` table only.
    """
    c = db()
    try:
        rows = c.execute(
            "SELECT ts, data FROM readings WHERE node=1 ORDER BY id DESC LIMIT 2000"
        ).fetchall()
    finally:
        c.close()
    rows.reverse()
    events = []
    prev_relay = None
    on_ts = None
    on_moisture = None
    for r in rows:
        d = json.loads(r["data"])
        relay = d.get("relay")
        if relay is None:
            continue
        relay = bool(relay)
        if prev_relay is None:
            prev_relay = relay
            if relay:
                on_ts = r["ts"]
                on_moisture = d.get("soil_moisture")
            continue
        if relay and not prev_relay:
            # transition: OFF -> ON
            on_ts = r["ts"]
            on_moisture = d.get("soil_moisture")
            events.append({"ts": r["ts"], "event": "on", "soil_moisture": on_moisture, "duration_s": None})
        elif not relay and prev_relay:
            # transition: ON -> OFF
            duration = round(r["ts"] - on_ts, 1) if on_ts is not None else None
            events.append({"ts": r["ts"], "event": "off", "soil_moisture": d.get("soil_moisture"),
                           "duration_s": duration})
            on_ts = None
        prev_relay = relay
    # Return most recent first, up to limit
    events = list(reversed(events))[:min(limit, 500)]
    return events


# Mount static files for PWA assets (icons, manifest, sw.js)
# index.html is still served explicitly via the route below
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/sw.js")
def sw():
    return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript")


@app.get("/manifest.json")
def manifest():
    return FileResponse(BASE / "static" / "manifest.json", media_type="application/manifest+json")
