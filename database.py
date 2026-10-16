import sqlite3
import threading
from datetime import datetime, timedelta

DATABASE_PATH = "data/history.db"


db = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
lock = threading.Lock()

db.execute("""
    CREATE TABLE IF NOT EXISTS visits(
    id INTEGER PRIMARY KEY,
    table_name TEXT,
    started TEXT,
    ended   TEXT,
    seconds INTEGER,
    guests  INTEGER
    )
    """)
db.execute("""
    CREATE TABLE IF NOT EXISTS snapshots(
    id INTEGER PRIMARY KEY,
    time    TEXT,
    occupied_tables INTEGER,
    guests  INTEGER
    )
    """)
db.commit()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_visit(table_name, seconds, guests):
    ended = datetime.now()
    started = ended - timedelta(seconds=seconds)
    with lock:
        db.execute("INSERT INTO visits (table_name, started, ended, seconds, guests) VALUES (?, ?, ?, ?, ?)",
            (table_name, started.strftime("%Y-%m-%d %H:%M:%S"), ended.strftime("%Y-%m-%d %H:%M:%S"),
             seconds, guests))
        db.commit()


def save_snapshot(occupied_tables, guests):
    with lock:
        db.execute("INSERT INTO snapshots (time, occupied_tables, guests) VALUES (?, ?, ?)",
            (now(), occupied_tables, guests))
        db.commit()


def query(sql, params=()):
    with lock:
        return [dict(row) for row in db.execute(sql, params)]


def table_summary():
    return query("""
        SELECT table_name,
               COUNT(*)              AS visits,
               ROUND(AVG(seconds))   AS average_seconds,
               MAX(seconds)          AS longest_seconds,
               ROUND(AVG(guests), 1) AS average_guests
        FROM visits
        GROUP BY table_name
        ORDER BY table_name
        """)


def recent_visits(limit=20):
    return query("SELECT table_name, ended, seconds, guests FROM visits ORDER BY id DESC LIMIT ?", (limit,))


def snapshots(seconds=None):

    if seconds is None:
        return query("SELECT time, occupied_tables, guests FROM snapshots ORDER BY id")
    since = (datetime.now() - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")
    return query("SELECT time, occupied_tables, guests FROM snapshots WHERE time >= ? ORDER BY id", (since,))


def counts():
    return query("SELECT (SELECT COUNT(*) FROM visits) AS visits, (SELECT COUNT(*) FROM snapshots) AS snapshots")[0]
