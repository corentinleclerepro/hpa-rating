import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from .referentiel import CURRENT_VERSION, LEGACY_VERSION

SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'camping',
    mention TEXT NOT NULL DEFAULT 'tourisme',
    target_stars INTEGER NOT NULL DEFAULT 3,
    profile TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    audit_id TEXT NOT NULL,
    criterion_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'TODO',
    notes TEXT NOT NULL DEFAULT '',
    validated_by TEXT NOT NULL DEFAULT '',
    validated_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (audit_id, criterion_id)
);
CREATE TABLE IF NOT EXISTS evidences (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    criterion_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    stale INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, message TEXT NOT NULL, criterion_id TEXT, step TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS activity_by_audit ON activity(audit_id, id DESC);
"""

STATUSES = ["TODO", "IN_PROGRESS", "EVIDENCE_MISSING", "NON_COMPLIANT", "VALIDATED"]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lock = threading.RLock()
        self.depth = 0
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._upgrade()

    def _upgrade(self):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            audit_columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(audits)")}
            if "reference_version" not in audit_columns:
                self.conn.execute("ALTER TABLE audits ADD COLUMN reference_version TEXT")
                self.conn.execute("""UPDATE audits SET reference_version = CASE WHEN
                    EXISTS (SELECT 1 FROM items WHERE audit_id = audits.id)
                    OR EXISTS (SELECT 1 FROM evidences WHERE audit_id = audits.id)
                    THEN ? ELSE ? END""", (LEGACY_VERSION, CURRENT_VERSION))
            if "owner_id" not in audit_columns:
                self.conn.execute("ALTER TABLE audits ADD COLUMN owner_id TEXT")
            if "resume_criterion" not in audit_columns:
                self.conn.execute("ALTER TABLE audits ADD COLUMN resume_criterion TEXT")
            if "profile_confirmed" not in audit_columns:
                self.conn.execute("ALTER TABLE audits ADD COLUMN profile_confirmed INTEGER NOT NULL DEFAULT 0")
                # Reuse information actually present in existing dossiers, without editing their items.
                from .workflow import profile_ready
                previous = self.conn.execute("SELECT id,profile FROM audits").fetchall()
                self.conn.executemany("UPDATE audits SET profile_confirmed=1 WHERE id=?",
                                      [(row["id"],) for row in previous if profile_ready(json.loads(row["profile"] or "{}"))])
            if "proofs_reviewed" not in audit_columns:
                self.conn.execute("ALTER TABLE audits ADD COLUMN proofs_reviewed INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("CREATE INDEX IF NOT EXISTS audits_owner ON audits(owner_id, updated_at)")
            item_columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(items)")}
            for col in ("awarded_points", "validated_stars"):
                if col not in item_columns:
                    self.conn.execute(f"ALTER TABLE items ADD COLUMN {col} INTEGER")

    @contextmanager
    def atomic(self, owner=None):
        with self.lock:
            outer = not self.depth
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self.depth += 1
            try:
                yield
            except BaseException:
                if outer:
                    self.conn.rollback()
                raise
            else:
                if outer:
                    self.conn.commit()
            finally:
                self.depth -= 1

    def _commit(self):
        if not self.depth:
            self.conn.commit()

    def close(self):
        self.conn.close()

    def _audit_row(self, row):
        d = dict(row)
        d["profile"] = json.loads(d["profile"] or "{}")
        return d

    def list_audits(self, owner=None):
        rows = self.conn.execute(
            """SELECT a.*,
                (SELECT COUNT(*) FROM items i WHERE i.audit_id = a.id) AS nb_items,
                (SELECT COUNT(*) FROM items i WHERE i.audit_id = a.id AND i.status = 'VALIDATED') AS nb_validated,
                (SELECT COUNT(*) FROM evidences e WHERE e.audit_id = a.id) AS nb_evidences
               FROM audits a WHERE (CAST(? AS TEXT) IS NULL OR a.owner_id = ?) ORDER BY a.updated_at DESC,
                    (SELECT MAX(id) FROM activity WHERE audit_id=a.id) DESC, a.id""", (owner, owner)
        ).fetchall()
        return [self._audit_row(r) for r in rows]

    def create_audit(self, name, type_, mention, target_stars, profile, reference_version=CURRENT_VERSION, owner=None):
        aid = uuid.uuid4().hex[:12]
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO audits (id, name, type, mention, target_stars, profile, created_at, updated_at, reference_version, owner_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, name, type_, mention, int(target_stars), json.dumps(profile or {}), ts, ts, reference_version, owner),
        )
        self._commit()
        return self.get_audit(aid)

    def get_audit(self, aid):
        row = self.conn.execute("SELECT * FROM audits WHERE id = ?", (aid,)).fetchone()
        return self._audit_row(row) if row else None

    def update_audit(self, aid, fields):
        allowed = {"name", "type", "mention", "target_stars", "profile"}
        sets = []
        vals = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "profile":
                v = json.dumps(v or {})
            if k == "target_stars":
                v = int(v)
            sets.append(f"{k} = ?")
            vals.append(v)
        if not sets:
            return self.get_audit(aid)
        sets.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(aid)
        self.conn.execute(f"UPDATE audits SET {', '.join(sets)} WHERE id = ?", vals)
        self._commit()
        return self.get_audit(aid)

    def delete_audit(self, aid):
        self.conn.execute("DELETE FROM activity WHERE audit_id = ?", (aid,))
        self.conn.execute("DELETE FROM evidences WHERE audit_id = ?", (aid,))
        self.conn.execute("DELETE FROM items WHERE audit_id = ?", (aid,))
        self.conn.execute("DELETE FROM audits WHERE id = ?", (aid,))
        self._commit()

    def clone_audit(self, aid, new_name):
        src = self.get_audit(aid)
        if not src:
            return None
        new = self.create_audit(new_name, src["type"], src["mention"], src["target_stars"], src["profile"], src["reference_version"], src["owner_id"])
        self.conn.execute("UPDATE audits SET profile_confirmed=? WHERE id=?", (src["profile_confirmed"], new["id"]))
        items = self.conn.execute("SELECT * FROM items WHERE audit_id = ?", (aid,)).fetchall()
        for it in items:
            self.conn.execute(
                """INSERT INTO items (audit_id, criterion_id, status, notes, validated_by, validated_at,
                   updated_at, awarded_points, validated_stars) VALUES (?,?,?,?,?,?,?,?,?)""",
                (new["id"], it["criterion_id"], it["status"], it["notes"], it["validated_by"], it["validated_at"],
                 now_iso(), it["awarded_points"], it["validated_stars"]),
            )
        evs = self.conn.execute("SELECT * FROM evidences WHERE audit_id = ?", (aid,)).fetchall()
        for ev in evs:
            new_eid = uuid.uuid4().hex[:12]
            self.conn.execute(
                "INSERT INTO evidences (id, audit_id, criterion_id, kind, filename, original_name, url, caption, stale, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_eid, new["id"], ev["criterion_id"], ev["kind"], ev["filename"], ev["original_name"], ev["url"], ev["caption"], 1, now_iso()),
            )
            if "object_key" in ev.keys() and ev["object_key"]:
                self.conn.execute("UPDATE evidences SET object_key=? WHERE id=?", (ev["object_key"], new_eid))
        self._commit()
        return self.get_audit(new["id"])

    def get_item(self, aid, cid):
        return self.conn.execute(
            "SELECT * FROM items WHERE audit_id = ? AND criterion_id = ?", (aid, cid)
        ).fetchone()

    def upsert_item(self, aid, cid, status, notes, validated_by, awarded_points=None, validated_stars=None):
        ts = now_iso()
        self.conn.execute(
            """INSERT INTO items (audit_id, criterion_id, status, notes, validated_by, validated_at, updated_at, awarded_points, validated_stars)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(audit_id, criterion_id) DO UPDATE SET
                 status = excluded.status, notes = excluded.notes,
                 validated_by = excluded.validated_by,
                 validated_at = excluded.validated_at, validated_stars = excluded.validated_stars,
                 awarded_points = excluded.awarded_points,
                 updated_at = excluded.updated_at""",
            (aid, cid, status, notes or "", (validated_by or "") if status == "VALIDATED" else "",
             ts if status == "VALIDATED" else None, ts, awarded_points, validated_stars if status == "VALIDATED" else None),
        )
        self._commit()
        return self.get_item(aid, cid)

    def list_items(self, aid):
        rows = self.conn.execute("SELECT * FROM items WHERE audit_id = ?", (aid,)).fetchall()
        return {r["criterion_id"]: dict(r) for r in rows}

    def add_evidence(self, aid, cid, kind, filename, original_name="", url="", caption=""):
        return self.add_evidences(aid, cid, [(kind, filename, original_name, url, caption)])[0]

    def add_evidences(self, aid, cid, records):
        rows = [(uuid.uuid4().hex[:12], aid, cid, *record, now_iso()) for record in records]
        with self.atomic():
            self.conn.executemany(
                "INSERT INTO evidences (id, audit_id, criterion_id, kind, filename, original_name, url, caption, stale, created_at) VALUES (?,?,?,?,?,?,?,?,0,?)",
                rows)
        return [self.get_evidence(row[0]) for row in rows]

    def get_evidence(self, eid):
        r = self.conn.execute("SELECT * FROM evidences WHERE id = ?", (eid,)).fetchone()
        return dict(r) if r else None

    def list_evidences(self, aid, cid=None):
        if cid:
            rows = self.conn.execute(
                "SELECT * FROM evidences WHERE audit_id = ? AND criterion_id = ? ORDER BY created_at", (aid, cid)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM evidences WHERE audit_id = ? ORDER BY created_at", (aid,)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_evidence(self, eid, caption=None, stale=None):
        ev = self.get_evidence(eid)
        if not ev:
            return None
        caption = ev["caption"] if caption is None else caption
        stale = ev["stale"] if stale is None else int(stale)
        self.conn.execute(
            "UPDATE evidences SET caption = ?, stale = ? WHERE id = ?", (caption, stale, eid)
        )
        self._commit()
        return self.get_evidence(eid)

    def demote_missing_evidence(self, aid, criterion_ids):
        self.conn.executemany("""UPDATE items SET status = 'EVIDENCE_MISSING', validated_by = '',
            validated_at = NULL, validated_stars = NULL, updated_at = ?
            WHERE audit_id = ? AND criterion_id = ? AND status = 'VALIDATED'
              AND NOT EXISTS (SELECT 1 FROM evidences e WHERE e.audit_id = items.audit_id
                              AND e.criterion_id = items.criterion_id)""",
            [(now_iso(), aid, cid) for cid in criterion_ids])

    def delete_evidence(self, evidence, needs_proof):
        with self.atomic():
            self.conn.execute("DELETE FROM evidences WHERE id = ?", (evidence["id"],))
            if needs_proof:
                self.demote_missing_evidence(evidence["audit_id"], [evidence["criterion_id"]])


    def log(self, aid, message, step="overview", criterion=None, at=None):
        stamp = at or now_iso()
        self.conn.execute("INSERT INTO activity(audit_id,created_at,message,criterion_id,step) VALUES(?,?,?,?,?)",
                          (aid, stamp, message, criterion, step))
        self.conn.execute("UPDATE audits SET updated_at=? WHERE id=?", (stamp, aid))
        self._commit()

    def history(self, aid):
        rows = self.conn.execute("SELECT created_at,message,criterion_id,step FROM activity WHERE audit_id=? ORDER BY id DESC", (aid,))
        return [dict(r) for r in rows]
