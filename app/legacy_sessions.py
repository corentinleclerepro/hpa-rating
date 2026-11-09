"""Keep logged-in guests on the switch to the independent guest session store."""
import sqlite3
from contextlib import closing
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection, transaction
from django.utils import timezone


def import_guest_sessions():
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS hpa_session_import (id INTEGER PRIMARY KEY)")
        cur.execute("INSERT OR IGNORE INTO hpa_session_import VALUES(1)")
        if not cur.rowcount:
            return
        source = settings.DATA_DIR / "access.sqlite3"
        if not source.is_file():
            return
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as old:
            if not old.execute("PRAGMA table_info(django_session)").fetchone():
                return
            codec = SessionStore()
            for key, encoded, expires in old.execute(
                    "SELECT session_key,session_data,expire_date FROM django_session WHERE expire_date > ?",
                    (timezone.now().strftime("%Y-%m-%d %H:%M:%S"),)):
                guest = codec.decode(encoded).get("guest")
                if isinstance(guest, list) and len(guest) == 2 and isinstance(guest[0], str) and isinstance(guest[1], int):
                    cur.execute("INSERT OR IGNORE INTO django_session(session_key,session_data,expire_date) VALUES(%s,%s,%s)",
                                [key, codec.encode({"guest": guest}), expires])
