import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

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
"""

STATUSES = ["TODO", "IN_PROGRESS", "EVIDENCE_MISSING", "NON_COMPLIANT", "VALIDATED"]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def _audit_row(self, row):
        d = dict(row)
        d["profile"] = json.loads(d["profile"] or "{}")
        return d

    def list_audits(self):
        rows = self.conn.execute(
            """SELECT a.*,
                (SELECT COUNT(*) FROM items i WHERE i.audit_id = a.id) AS nb_items,
                (SELECT COUNT(*) FROM items i WHERE i.audit_id = a.id AND i.status = 'VALIDATED') AS nb_validated,
                (SELECT COUNT(*) FROM evidences e WHERE e.audit_id = a.id) AS nb_evidences
               FROM audits a ORDER BY a.updated_at DESC"""
        ).fetchall()
        return [self._audit_row(r) for r in rows]

    def create_audit(self, name, type_, mention, target_stars, profile):
        aid = uuid.uuid4().hex[:12]
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO audits (id, name, type, mention, target_stars, profile, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (aid, name, type_, mention, int(target_stars), json.dumps(profile or {}), ts, ts),
        )
        self.conn.commit()
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
        self.conn.commit()
        return self.get_audit(aid)

    def delete_audit(self, aid):
        self.conn.execute("DELETE FROM evidences WHERE audit_id = ?", (aid,))
        self.conn.execute("DELETE FROM items WHERE audit_id = ?", (aid,))
        self.conn.execute("DELETE FROM audits WHERE id = ?", (aid,))
        self.conn.commit()

    def clone_audit(self, aid, new_name):
        src = self.get_audit(aid)
        if not src:
            return None
        new = self.create_audit(new_name, src["type"], src["mention"], src["target_stars"], src["profile"])
        items = self.conn.execute("SELECT * FROM items WHERE audit_id = ?", (aid,)).fetchall()
        for it in items:
            self.conn.execute(
                "INSERT INTO items (audit_id, criterion_id, status, notes, validated_by, validated_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (new["id"], it["criterion_id"], it["status"], it["notes"], it["validated_by"], it["validated_at"], now_iso()),
            )
        evs = self.conn.execute("SELECT * FROM evidences WHERE audit_id = ?", (aid,)).fetchall()
        for ev in evs:
            new_eid = uuid.uuid4().hex[:12]
            self.conn.execute(
                "INSERT INTO evidences (id, audit_id, criterion_id, kind, filename, original_name, url, caption, stale, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_eid, new["id"], ev["criterion_id"], ev["kind"], ev["filename"], ev["original_name"], ev["url"], ev["caption"], 1, now_iso()),
            )
        self.conn.commit()
        return new

    def get_item(self, aid, cid):
        return self.conn.execute(
            "SELECT * FROM items WHERE audit_id = ? AND criterion_id = ?", (aid, cid)
        ).fetchone()

    def upsert_item(self, aid, cid, status, notes, validated_by):
        ts = now_iso()
        cur = self.conn.execute(
            """INSERT INTO items (audit_id, criterion_id, status, notes, validated_by, validated_at, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(audit_id, criterion_id) DO UPDATE SET
                 status = excluded.status, notes = excluded.notes,
                 validated_by = excluded.validated_by,
                 validated_at = CASE WHEN excluded.status = 'VALIDATED' THEN excluded.updated_at ELSE items.validated_at END,
                 updated_at = excluded.updated_at""",
            (aid, cid, status, notes or "", validated_by or "", ts, ts),
        )
        self.conn.commit()
        return self.get_item(aid, cid)

    def list_items(self, aid):
        rows = self.conn.execute("SELECT * FROM items WHERE audit_id = ?", (aid,)).fetchall()
        return {r["criterion_id"]: dict(r) for r in rows}

    def add_evidence(self, aid, cid, kind, filename, original_name="", url="", caption=""):
        eid = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO evidences (id, audit_id, criterion_id, kind, filename, original_name, url, caption, stale, created_at) VALUES (?,?,?,?,?,?,?,?,0,?)",
            (eid, aid, cid, kind, filename, original_name, url, caption, now_iso()),
        )
        self.conn.commit()
        return self.get_evidence(eid)

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
        self.conn.commit()
        return self.get_evidence(eid)

    def delete_evidence(self, eid):
        self.conn.execute("DELETE FROM evidences WHERE id = ?", (eid,))
        self.conn.commit()
