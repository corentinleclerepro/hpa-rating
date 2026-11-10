"""Private PostgreSQL evidence files; all writes participate in the dossier transaction."""
import re
import uuid
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.http import content_disposition_header
from hpa_shared.http import payload, error
from .exporters import evidence_kind, safe_filename

CHUNK = 1024 * 1024
MAX_TOTAL = 64 * CHUNK


def new_blob(db, size):
    key = uuid.uuid4().hex
    db.conn.execute("INSERT INTO file_blobs(id,size_bytes) VALUES(?,?)", (key, size))
    return key


def save_bytes(db, data):
    key = new_blob(db, len(data))
    db.conn.executemany("INSERT INTO file_chunks(file_id,part,content) VALUES(?,?,?)",
                        [(key, start // CHUNK, data[start:start+CHUNK]) for start in range(0, len(data), CHUNK)])
    return key


def attach(db, aid, cid, key, original, filename, caption, kind=None):
    proof = db.add_evidence(aid, cid, kind or evidence_kind(original), filename, original, caption=caption)
    db.conn.execute("UPDATE evidences SET object_key=? WHERE id=?", (key, proof["id"]))
    return proof


def next_sequence(db, aid, cid):
    matches = (re.match(r"^C\d+_(\d+)_", row["filename"]) for row in db.list_evidences(aid, cid))
    return 1 + max((int(match[1]) for match in matches if match), default=0)


def register(db, aid, cid, key, original, caption):
    filename = safe_filename(cid, next_sequence(db, aid, cid), original)
    proof = attach(db, aid, cid, key, original, filename, caption)
    db.log(aid, "Justificatif ajouté · " + original, "proofs", cid)
    return proof


def chunks(db, key):
    size = db.conn.execute("SELECT size_bytes FROM file_blobs WHERE id=?", (key,)).fetchone()
    if size is None:
        raise FileNotFoundError
    for part in range((size["size_bytes"] + CHUNK - 1) // CHUNK):
        row = db.conn.execute("SELECT content FROM file_chunks WHERE file_id=? AND part=?", (key, part)).fetchone()
        if row is None:
            raise OSError("Le justificatif est incomplet.")
        yield bytes(row["content"])


def download(db, proof, mime):
    response = StreamingHttpResponse(chunks(db, proof["object_key"]), content_type=mime)
    response["Content-Disposition"] = content_disposition_header(mime == "application/octet-stream", proof["original_name"])
    return response


def prepare(api, aid, cid):
    files = payload(api.request).get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 195:
        raise ValueError("Sélectionnez entre 1 et 195 fichiers.")
    entries = []
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("Fichier invalide.")
        name, size, caption = file.get("name"), file.get("size"), file.get("caption", "")
        if (not isinstance(name, str) or not 1 <= len(name) <= 255 or any(ord(c)<32 or c in "/\\" for c in name)
                or type(size) is not int or not 0 <= size <= MAX_TOTAL or not isinstance(caption, str)):
            raise ValueError("Nom ou taille du justificatif invalide.")
        entries.append((name, size, caption))
    if sum(entry[1] for entry in entries) > MAX_TOTAL:
        return error("Envoyez au maximum 64 Mo à la fois.", 413)
    db = api.db
    db.conn.execute("""DELETE FROM pending_files WHERE id IN
                    (SELECT id FROM pending_files WHERE expires_at<=CURRENT_TIMESTAMP ORDER BY expires_at LIMIT 100)""")
    keys = []
    for name, size, caption in entries:
        key = new_blob(db, size)
        db.conn.execute("INSERT INTO pending_files(id,audit_id,criterion_id,owner_id,original_name,size_bytes,caption) VALUES(?,?,?,?,?,?,?)",
                        (key, aid, cid, api.owner, name, size, caption))
        keys.append(key)
    return JsonResponse({"files":keys,"chunk_bytes":CHUNK}, status=201)


def ticket(api, aid, cid, key):
    row = api.db.conn.execute("""SELECT * FROM pending_files WHERE id=? AND audit_id=? AND criterion_id=?
                             AND owner_id=? AND expires_at>CURRENT_TIMESTAMP""", (key,aid,cid,api.owner)).fetchone()
    if not row:
        raise FileNotFoundError
    return row


def put_part(api, aid, cid, key, number):
    row = ticket(api, aid, cid, key)
    expected = min(CHUNK, row["size_bytes"] - number * CHUNK)
    if expected <= 0 or int(api.request.META.get("CONTENT_LENGTH") or 0) > CHUNK:
        raise ValueError("Taille de la partie invalide.")
    content = api.request.body
    if len(content) != expected:
        raise ValueError("L’envoi de cette partie est incomplet.")
    stored = api.db.conn.execute("""INSERT INTO file_chunks(file_id,part,content) VALUES(?,?,?)
                                  ON CONFLICT(file_id,part) DO NOTHING""", (key,number,content))
    if not stored.rowcount and not api.db.conn.execute(
            "SELECT 1 FROM file_chunks WHERE file_id=? AND part=? AND content=?", (key,number,content)).fetchone():
        return error("Cette partie a déjà été reçue avec un contenu différent.", 409)
    return JsonResponse({"received":len(content)})


def finish(api, aid, cid):
    keys = payload(api.request).get("files")
    if (not isinstance(keys,list) or not 1 <= len(keys) <= 195 or
            not all(isinstance(k,str) and re.fullmatch(r"[0-9a-f]{32}",k) for k in keys) or len(set(keys)) != len(keys)):
        raise ValueError("Liste des justificatifs invalide.")
    db = api.db
    rows = [ticket(api, aid, cid, key) for key in keys]
    for row in rows:
        actual = db.conn.execute("SELECT COALESCE(SUM(octet_length(content)),0) AS size FROM file_chunks WHERE file_id=?",
                                 (row["id"],)).fetchone()["size"]
        if actual != row["size_bytes"]:
            return error("Le fichier est incomplet. Reprenez l’envoi.", 409)
    created = []
    for row in rows:
        if row["evidence_id"]:
            created.append(db.get_evidence(row["evidence_id"]))
            continue
        proof = register(db, aid, cid, row["id"], row["original_name"], row["caption"])
        db.conn.execute("UPDATE pending_files SET evidence_id=? WHERE id=?", (proof["id"],row["id"]))
        created.append(proof)
        api.revisit_proofs(aid)
    return JsonResponse({"evidences":created}, status=201)
