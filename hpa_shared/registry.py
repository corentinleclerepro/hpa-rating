"""Invitation identities shared between the public app and the operator console."""
import hashlib
import hmac
import ipaddress
import os
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from django.conf import settings
from .http import error


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(kind, value):
    key = settings.INVITATION_KEY if kind == "invite" else settings.APPLICATION_KEY
    return hmac.new(key.encode(), (kind + ":" + value).encode(), hashlib.sha256).hexdigest()


def canonical(value):
    return "".join(str(value).upper().split()).replace("-", "")[:128]


LIMITS = "CREATE TABLE login_limits (bucket TEXT PRIMARY KEY, since INTEGER NOT NULL, failures INTEGER NOT NULL)"


class Store:
    def __init__(self, filename, initialize, directory=None):
        self.lock = threading.RLock()
        directory = directory or settings.DATA_DIR
        self.conn = sqlite3.connect(directory / filename, check_same_thread=False, timeout=20)
        self.conn.row_factory = sqlite3.Row
        with self.atomic():
            if self.conn.execute("PRAGMA user_version").fetchone()[0] == 0:
                legacy = directory / "app.db"
                if legacy.exists():
                    with closing(sqlite3.connect(legacy.as_uri() + "?mode=ro", uri=True)) as old:
                        initialize(self.conn, old)
                else:
                    initialize(self.conn, None)
                self.conn.execute("PRAGMA user_version = 1")

    @contextmanager
    def atomic(self):
        with self.lock:
            outer = not self.conn.in_transaction
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                if outer:
                    self.conn.commit()
            except BaseException:
                if outer:
                    self.conn.rollback()
                raise


def legacy_columns(old, table):
    return {r[1] for r in old.execute("PRAGMA table_info(" + table + ")")} if old is not None else set()


def copy_limits(conn, old):
    conn.execute(LIMITS)
    if legacy_columns(old, "login_limits"):
        conn.executemany("INSERT INTO login_limits VALUES(?,?,?)",
                         old.execute("SELECT bucket,since,failures FROM login_limits WHERE since >= ?", (int(time.time())-600,)))


def init_invitations(conn, old):
    conn.execute("""CREATE TABLE guests (
        id TEXT PRIMARY KEY, label TEXT NOT NULL, digest TEXT UNIQUE, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, last_seen TEXT, revoked INTEGER NOT NULL DEFAULT 0, code_used INTEGER NOT NULL DEFAULT 0)""")
    cols = legacy_columns(old, "guests")
    if cols:
        used = "code_used" if "code_used" in cols else "last_seen IS NOT NULL"
        conn.executemany("INSERT INTO guests VALUES(?,?,?,?,?,?,?,?)", old.execute(
            "SELECT id,label,digest,version,created_at,last_seen,revoked," + used + " FROM guests"))
    copy_limits(conn, old)


@lru_cache(maxsize=1)
def registry():
    if settings.CLOUD_ROLE:
        from .postgres import PgStore
        return PgStore("hpa_registry" if settings.CLOUD_ROLE == "admin" else "default")
    db = Store("invitations.sqlite3", init_invitations, settings.REGISTRY_DIR)
    with db.atomic():
        db.conn.execute("""CREATE TABLE IF NOT EXISTS access_requests (
            id TEXT PRIMARY KEY, camping TEXT NOT NULL, email TEXT NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','declined')),
            decided_at TEXT, guest_id TEXT REFERENCES guests(id))""")
        db.conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS pending_access_email
                           ON access_requests(email) WHERE status IN ('pending','approved')""")
        if db.conn.execute("PRAGMA user_version").fetchone()[0] < 2:
            db.conn.execute("""CREATE TRIGGER erase_refused_request AFTER UPDATE OF status ON access_requests
                WHEN OLD.status='pending' AND NEW.status='declined'
                BEGIN DELETE FROM access_requests WHERE id=NEW.id AND status='declined'; END""")
            db.conn.execute("DELETE FROM access_requests WHERE status='declined'")
            db.conn.execute("PRAGMA user_version = 2")
    return db


def throttled(db, request, purpose):
    address = request.META.get("REMOTE_ADDR", "local")
    if settings.CLOUD_ROLE and os.environ.get("VERCEL") == "1":
        # Vercel overwrites this header at its public ingress.
        forwarded = request.headers.get("X-Vercel-Forwarded-For", "").split(",")[-1].strip()
        try:
            address = str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    bucket = digest("limits", purpose + "/" + address)
    if hasattr(db, "lock_key"):
        db.lock_key("tentatives/" + bucket)
    now = int(time.time())
    db.conn.execute("DELETE FROM login_limits WHERE since < ?", (now - 600,))
    row = db.conn.execute("SELECT failures FROM login_limits WHERE bucket=?", (bucket,)).fetchone()
    if row and row["failures"] >= 10:
        return None
    db.conn.execute("""INSERT INTO login_limits VALUES(?,?,1) ON CONFLICT(bucket)
                   DO UPDATE SET failures=login_limits.failures+1""", (bucket, now))
    return bucket


def limited():
    reply = error("Trop de tentatives. Réessayez dans dix minutes.", 429)
    reply["Retry-After"] = "600"
    return reply
