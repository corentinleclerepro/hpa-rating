"""Run existing Hpa queries on the application's restricted PostgreSQL role."""
from contextlib import contextmanager, nullcontext
import os
import re
from pathlib import Path
from django.db import connections, transaction


def database(role):
    host = os.environ["HPA_DB_HOST"]
    project = os.environ["HPA_SUPABASE_PROJECT"]
    if not re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", host) or not re.fullmatch(r"[a-z0-9]{20}", project):
        raise ValueError("Adresse de connexion Supabase invalide.")
    return {"ENGINE":"django.db.backends.postgresql", "NAME":"postgres", "HOST":host, "PORT":"6543",
            "USER":f"hpa_rating_{role}.{project}", "PASSWORD":os.environ["HPA_DB_PASSWORD"],
            "CONN_MAX_AGE":0, "OPTIONS":{"sslmode":"verify-full","sslrootcert":str(Path(__file__).with_name("supabase-root-2021.crt")),
                                         "prepare_threshold":None,"connect_timeout":8}}


class Rows(list):
    def fetchone(self):
        return self[0] if self else None

    def fetchall(self):
        return self


class PgQueries:
    def __init__(self, alias):
        self.alias = alias

    def execute(self, sql, params=()):
        with connections[self.alias].cursor() as cur:
            cur.execute(sql.replace("?", "%s"), params)
            result = Rows()
            if cur.description:
                cols = [col[0] for col in cur.description]
                result.extend(dict(zip(cols, row)) for row in cur.fetchall())
            result.rowcount = cur.rowcount
            return result

    def executemany(self, sql, rows):
        with connections[self.alias].cursor() as cur:
            cur.executemany(sql.replace("?", "%s"), rows)


class PgStore:
    def __init__(self, alias):
        self.conn = PgQueries(alias)
        self.lock = nullcontext()

    @contextmanager
    def atomic(self, owner=None):
        with transaction.atomic(using=self.conn.alias):
            if owner is not None:
                self.lock_key("dossier/" + owner)
            yield

    def lock_key(self, value):
        self.conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 9173))", (value,))

    def _commit(self):
        # Django commits the enclosing operation, or uses autocommit for a standalone statement.
        pass
