from functools import lru_cache
from django.conf import settings
from hpa_shared.registry import Store, copy_limits, legacy_columns


def initialize(conn, old):
    conn.execute("CREATE TABLE local_setup (id INTEGER PRIMARY KEY CHECK (id=1), digest TEXT NOT NULL, expires INTEGER NOT NULL)")
    conn.execute("CREATE TABLE recovery_codes (digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL)")
    if legacy_columns(old, "local_setup"):
        conn.executemany("INSERT INTO local_setup VALUES(?,?,?)", old.execute("SELECT id,digest,expires FROM local_setup"))
    if legacy_columns(old, "recovery_codes"):
        conn.executemany("INSERT INTO recovery_codes VALUES(?,?)", old.execute("SELECT digest,user_id FROM recovery_codes"))
    copy_limits(conn, old)


@lru_cache(maxsize=1)
def private_store():
    if settings.WEB_ADMIN:
        from hpa_shared.postgres import PgStore
        return PgStore("default")
    db = Store("console-state.sqlite3", initialize)
    with db.atomic():
        db.conn.execute("""CREATE TABLE IF NOT EXISTS admin_email_challenge (
            id INTEGER PRIMARY KEY CHECK (id=1), nonce TEXT NOT NULL, proof TEXT NOT NULL,
            sent_at INTEGER NOT NULL, expires INTEGER NOT NULL, failures INTEGER NOT NULL)""")
    return db
