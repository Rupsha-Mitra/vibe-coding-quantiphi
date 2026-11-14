"""SQLite cache + settings store.

Everything fetched from GitHub is stored here with a timestamp so the
dashboard can serve repeat page loads without touching the API, and can fall
back to stale data when GitHub rate-limits us.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("PORTFOLIO_DB", os.path.join(os.path.dirname(__file__), "portfolio.db"))

DEFAULT_SETTINGS = {
    "default_username": "",
    "cache_ttl_minutes": 60,
    "theme": "dark",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    login      TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS repos (
    login      TEXT NOT NULL,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (login, name)
);
CREATE TABLE IF NOT EXISTS contributions (
    login      TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    source     TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_descriptions (
    login      TEXT PRIMARY KEY,
    text       TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


@contextmanager
def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path=None):
    with connect(path) as c:
        c.executescript(SCHEMA)


# ---------- settings ----------
def get_settings():
    with connect() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    out = dict(DEFAULT_SETTINGS)
    for r in rows:
        out[r["key"]] = json.loads(r["value"])
    return out


def save_settings(updates):
    allowed = {k: v for k, v in updates.items() if k in DEFAULT_SETTINGS}
    if "cache_ttl_minutes" in allowed:
        allowed["cache_ttl_minutes"] = max(1, min(int(allowed["cache_ttl_minutes"]), 1440))
    if "theme" in allowed and allowed["theme"] not in ("dark", "light"):
        allowed["theme"] = "dark"
    if "default_username" in allowed:
        allowed["default_username"] = str(allowed["default_username"]).strip()[:39]
    with connect() as c:
        for k, v in allowed.items():
            c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (k, json.dumps(v)))
    return get_settings()


def ttl_seconds():
    return get_settings()["cache_ttl_minutes"] * 60


# ---------- cache helpers ----------
def is_fresh(fetched_at, ttl=None):
    return (time.time() - fetched_at) < (ttl if ttl is not None else ttl_seconds())


def get_profile(login):
    with connect() as c:
        r = c.execute("SELECT data, fetched_at FROM profiles WHERE login = ?", (login.lower(),)).fetchone()
    return (json.loads(r["data"]), r["fetched_at"]) if r else (None, None)


def put_profile(login, data):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?)", (login.lower(), json.dumps(data), time.time()))


def get_repos(login):
    with connect() as c:
        rows = c.execute("SELECT data, fetched_at FROM repos WHERE login = ?", (login.lower(),)).fetchall()
    if not rows:
        return None, None
    return [json.loads(r["data"]) for r in rows], min(r["fetched_at"] for r in rows)


def put_repos(login, repos):
    now = time.time()
    with connect() as c:
        c.execute("DELETE FROM repos WHERE login = ?", (login.lower(),))
        c.executemany(
            "INSERT INTO repos VALUES (?, ?, ?, ?)",
            [(login.lower(), r["name"], json.dumps(r), now) for r in repos],
        )


def get_contributions(login):
    with connect() as c:
        r = c.execute(
            "SELECT data, source, fetched_at FROM contributions WHERE login = ?", (login.lower(),)
        ).fetchone()
    return (json.loads(r["data"]), r["source"], r["fetched_at"]) if r else (None, None, None)


def put_contributions(login, days, source):
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO contributions VALUES (?, ?, ?, ?)",
            (login.lower(), json.dumps(days), source, time.time()),
        )


# ---------- job description (vibe check) ----------
def get_jd(login):
    with connect() as c:
        r = c.execute("SELECT text FROM job_descriptions WHERE login = ?", (login.lower(),)).fetchone()
    return r["text"] if r else ""


def put_jd(login, text):
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO job_descriptions VALUES (?, ?, ?)", (login.lower(), text, time.time())
        )


def clear_cache(login=None):
    with connect() as c:
        for t in ("profiles", "repos", "contributions"):
            if login:
                c.execute(f"DELETE FROM {t} WHERE login = ?", (login.lower(),))
            else:
                c.execute(f"DELETE FROM {t}")
