"""Alerts log API. Teammate B owns this file. Alerts are sent by tools/alert_worker.py."""
import sqlite3
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException

DB = Path(__file__).resolve().parent.parent / "iiaas.db"
router = APIRouter()
ACTIVE_S = 1800  # an alert counts as "active" for 30 minutes unless someone dismisses it


def ensure(c):
    c.execute("CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, ts REAL, node INT, level TEXT, "
              "msg TEXT, channel TEXT, sent INT, acked INT DEFAULT 0)")
    try:
        c.execute("ALTER TABLE alerts ADD COLUMN acked INT DEFAULT 0")  # for databases made before this column
    except sqlite3.OperationalError:
        pass  # the column already exists


@router.get("/api/alerts")
def list_alerts(limit: int = 50, active: int = 0):
    """Newest first. active=1 returns only alerts from the last 30 minutes that nobody dismissed."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        ensure(c)
        q, args = "SELECT * FROM alerts", []
        if active:
            q += " WHERE acked = 0 AND ts > ?"
            args.append(time.time() - ACTIVE_S)
        rows = c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, min(limit, 500))).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


@router.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    c = sqlite3.connect(DB)
    try:
        with c:
            ensure(c)
            n = c.execute("UPDATE alerts SET acked = 1 WHERE id = ?", (alert_id,)).rowcount
    finally:
        c.close()
    if not n:
        raise HTTPException(404, "no such alert")
    return {"ok": True}