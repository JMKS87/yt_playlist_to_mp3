"""Schemat SQLite, połączenia i zapytania."""
import os
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id     TEXT PRIMARY KEY,
    title        TEXT,
    channel      TEXT,
    upload_date  TEXT,
    file_path    TEXT NOT NULL,
    quality      INTEGER NOT NULL,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    quality    INTEGER NOT NULL,
    out_dir    TEXT NOT NULL,
    overwrite  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    parent_id  INTEGER REFERENCES job_items(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('video', 'playlist')),
    yt_id      TEXT NOT NULL,
    title      TEXT,
    status     TEXT NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued', 'running', 'done', 'skipped', 'error')),
    message    TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_items_job ON job_items(job_id);
CREATE INDEX IF NOT EXISTS idx_job_items_status ON job_items(status);
"""

# Filmy z playlisty idą zaraz po niej, a zlecenia po kolei.
ITEM_ORDER = "job_id, COALESCE(parent_id, id), id"


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path):
    """Tworzy schemat i przywraca do kolejki pozycje przerwane restartem."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        with conn:
            conn.execute(
                "UPDATE job_items SET status = 'queued', updated_at = ? WHERE status = 'running'",
                (utcnow(),),
            )
    finally:
        conn.close()


# --- połączenie per request -------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


# --- zlecenia ---------------------------------------------------------------

def create_job(conn, quality, out_dir, overwrite, items):
    now = utcnow()
    with conn:
        cur = conn.execute(
            "INSERT INTO jobs (created_at, quality, out_dir, overwrite) VALUES (?, ?, ?, ?)",
            (now, quality, out_dir, int(overwrite)),
        )
        job_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO job_items (job_id, kind, yt_id, updated_at) VALUES (?, ?, ?, ?)",
            [(job_id, kind, yt_id, now) for kind, yt_id in items],
        )
    return job_id


def get_job(conn, job_id):
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def next_queued_item(conn):
    return conn.execute(
        f"SELECT * FROM job_items WHERE status = 'queued' ORDER BY {ITEM_ORDER} LIMIT 1"
    ).fetchone()


def set_item_status(conn, item_id, status, message=None, title=None):
    with conn:
        conn.execute(
            "UPDATE job_items SET status = ?, message = ?, title = COALESCE(?, title), updated_at = ?"
            " WHERE id = ?",
            (status, message, title, utcnow(), item_id),
        )


def finish_playlist(conn, item, title, entries):
    """Wstawia filmy z playlisty i zamyka jej pozycję w jednej transakcji.

    entries: lista (video_id, title, error_message | None).
    """
    now = utcnow()
    with conn:
        conn.executemany(
            "INSERT INTO job_items (job_id, parent_id, kind, yt_id, title, status, message, updated_at)"
            " VALUES (?, ?, 'video', ?, ?, ?, ?, ?)",
            [
                (item["job_id"], item["id"], vid, vtitle, "error" if err else "queued", err, now)
                for vid, vtitle, err in entries
            ],
        )
        conn.execute(
            "UPDATE job_items SET status = 'done', title = ?, message = ?, updated_at = ? WHERE id = ?",
            (title, f"filmów: {len(entries)}", now, item["id"]),
        )


def video_done_in_job(conn, job_id, video_id):
    return conn.execute(
        "SELECT 1 FROM job_items WHERE job_id = ? AND kind = 'video' AND yt_id = ? AND status = 'done'",
        (job_id, video_id),
    ).fetchone() is not None


def recent_jobs(conn, limit=20):
    jobs = [dict(row) for row in conn.execute(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
    )]
    if not jobs:
        return []
    by_id = {job["id"]: job for job in jobs}
    for job in jobs:
        job["entries"] = []
    placeholders = ",".join("?" * len(by_id))
    for row in conn.execute(
        f"SELECT * FROM job_items WHERE job_id IN ({placeholders}) ORDER BY {ITEM_ORDER}",
        list(by_id),
    ):
        by_id[row["job_id"]]["entries"].append(row)
    return jobs


def has_active_items(conn):
    return conn.execute(
        "SELECT 1 FROM job_items WHERE status IN ('queued', 'running') LIMIT 1"
    ).fetchone() is not None


# --- ewidencja filmów -------------------------------------------------------

def get_video(conn, video_id):
    return conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()


def upsert_video(conn, video_id, title, channel, upload_date, file_path, quality):
    with conn:
        conn.execute(
            """
            INSERT INTO videos (video_id, title, channel, upload_date, file_path, quality, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                title = excluded.title,
                channel = excluded.channel,
                upload_date = excluded.upload_date,
                file_path = excluded.file_path,
                quality = excluded.quality,
                processed_at = excluded.processed_at
            """,
            (video_id, title, channel, upload_date, file_path, quality, utcnow()),
        )


def list_videos(conn):
    return conn.execute("SELECT * FROM videos ORDER BY processed_at DESC, rowid DESC").fetchall()
