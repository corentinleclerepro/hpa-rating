import filecmp
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from .db import DB
from .exporters import STATUS_LABELS

SAMPLE = Path(__file__).parent / "sample"
LEGACY_DEMO_ID = "2c4414075d37"


def snapshot_legacy(root):
    source = root / "app.db"
    if not source.is_file():
        return
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as conn:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(audits)")]
        if not columns or {"owner_id", "profile_confirmed", "proofs_reviewed"}.issubset(columns):
            return
        old_public_storage = "owner_id" not in columns
        backup_dir = root / "migration-backups"
        backup_dir.mkdir(exist_ok=True)
        label = "avant-espaces-" if old_public_storage else "avant-parcours-"
        destination = backup_dir / (label + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        destination.mkdir()
        with closing(sqlite3.connect(destination / "app.db")) as dest:
            conn.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IOError("La sauvegarde du dossier n’a pas pu être vérifiée.")
        for name in ("dossiers", "exports"):
            if (root / name).exists():
                shutil.copytree(root / name, destination / name)
        # These generated ZIPs used a shared filename. Keep the pre-migration copy outside the serving paths.
        if old_public_storage and (root / "exports").is_dir():
            for original in (root / "exports").glob("*.zip"):
                saved = destination / "exports" / original.name
                if not filecmp.cmp(original, saved, shallow=False):
                    raise IOError("La sauvegarde de l’export a échoué.")
                original.unlink()


@lru_cache(maxsize=1)
def store():
    if settings.CLOUD_ROLE:
        from hpa_shared.postgres import PgStore
        class PostgresDossiers(PgStore, DB):
            pass
        return PostgresDossiers("default")
    snapshot_legacy(settings.DATA_DIR)
    return DB(str(settings.DATA_DIR / "app.db"))


def sample_audit(db, owner):
    spec = json.loads((SAMPLE / "camping.json").read_text(encoding="utf8"))
    sample = spec["audit"]
    audit = db.create_audit(sample["name"], sample["type"], sample["mention"], sample["target_stars"],
                            sample["profile"], sample["reference_version"], owner)
    aid = audit["id"]
    folder = settings.DATA_DIR / "dossiers" / aid
    try:
        for row in spec["items"]:
            db.upsert_item(aid, row["criterion_id"], row["status"], row["notes"], row["validated_by"], row["awarded_points"], row["validated_stars"])
            db.log(aid, f"Critère {row['criterion_id']} repris de l’exemple · {STATUS_LABELS[row['status']]}.", "criteria", row["criterion_id"])
        for proof in spec["evidences"]:
            cid = proof["criterion_id"]
            if settings.CLOUD_ROLE:
                from . import cloudfiles
                key = cloudfiles.save_bytes(db, (SAMPLE / proof["original_name"]).read_bytes())
                cloudfiles.attach(db, aid, cid, key, proof["original_name"], proof["filename"], proof["caption"], proof["kind"])
            else:
                location = folder / "evidences" / cid
                location.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SAMPLE / proof["original_name"], location / proof["filename"])
                db.add_evidence(aid, cid, proof["kind"], proof["filename"], proof["original_name"], caption=proof["caption"])
            db.log(aid, "Justificatif importé · " + proof["original_name"], "proofs", cid)
        db.log(aid, "Exemple 3 étoiles créé avec 7 critères renseignés et 3 justificatifs.")
        db.conn.execute("UPDATE audits SET profile_confirmed=1 WHERE id=?", (aid,))
        return db.get_audit(aid)
    except BaseException:
        if folder.is_dir():
            shutil.rmtree(folder)
        raise


def attach_previous(db, owner):
    """Only a local provisioning command can claim a pre-authentication dossier."""
    for audit in db.list_audits():
        if audit["owner_id"]:
            continue
        aid = audit["id"]
        events = [(audit["created_at"], "Dossier créé.", "profile", None)]
        items = sorted(db.list_items(aid).values(), key=lambda row: row["updated_at"])
        for row in items:
            cid = row["criterion_id"]
            events.append((row["updated_at"], f"Critère {cid} · {STATUS_LABELS[row['status']]}.", "criteria", cid))
        for ev in db.list_evidences(aid):
            events.append((ev["created_at"], "Justificatif ajouté · " + ev["original_name"], "proofs", ev["criterion_id"]))
        for stamp, label, step, cid in sorted(events, key=lambda entry: entry[0]):
            db.log(aid, label, step, cid, at=stamp)
        resume = "21" if aid == LEGACY_DEMO_ID else (items[-1]["criterion_id"] if items else None)
        db.conn.execute("UPDATE audits SET owner_id=?,resume_criterion=? WHERE id=?", (owner, resume, aid))
        db.log(aid, "Dossier existant rattaché à cet espace privé.")
