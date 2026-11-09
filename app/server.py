import json
import os
import re
import shutil
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

from . import scoring
from .db import DB, STATUSES
from .exporters import build_book_html, build_manifest, build_zip, evidence_kind, safe_filename, zip_path_for
from .referentiel import load as load_ref, criteria_index, stats as ref_stats

db = DB(os.path.join(DATA_DIR, "app.db"))


def parse_multipart(body, content_type):
    m = re.search(r"boundary=([^;]+)", content_type or "")
    if not m:
        return []
    boundary = m.group(1).strip().strip('"').encode()
    parts = []
    for chunk in body.split(b"--" + boundary):
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        if chunk.endswith(b"--"):
            chunk = chunk[:-2].rstrip(b"\r\n")
        head, _, content = chunk.partition(b"\r\n\r\n")
        headers = head.decode("utf-8", "replace")
        disp = re.search(r'name="([^"]+)"(?:;\s*filename="([^"]*)")?', headers)
        ctype = re.search(r"Content-Type:\s*([^\r\n]+)", headers)
        if not disp:
            continue
        parts.append({
            "name": disp.group(1),
            "filename": disp.group(2) if disp.group(2) else None,
            "content_type": ctype.group(1).strip() if ctype else "application/octet-stream",
            "data": content,
        })
    return parts


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PrepaClassement/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code, message):
        self._send_json({"error": message}, code)

    def _send_file(self, path, content_type, download_name=None):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _json_body(self):
        raw = self._body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_PATCH(self):
        self._route("PATCH")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if method == "GET" and path in ("/", "/index.html"):
            return self._send_file(os.path.join(STATIC_DIR, "index.html"), CONTENT_TYPES[".html"])
        if method == "GET" and path.startswith("/static/"):
            fname = os.path.basename(path)
            fpath = os.path.join(STATIC_DIR, fname)
            if os.path.isfile(fpath):
                ext = os.path.splitext(fname)[1]
                return self._send_file(fpath, CONTENT_TYPES.get(ext, "application/octet-stream"))
            return self._send_error(404, "statique introuvable")

        routes = [
            ("GET", r"^/api/meta$", self.api_meta),
            ("GET", r"^/api/referentiel$", self.api_referentiel),
            ("GET", r"^/api/referentiel/stats$", self.api_ref_stats),
            ("GET", r"^/api/audits$", self.api_list_audits),
            ("POST", r"^/api/audits$", self.api_create_audit),
            ("GET", r"^/api/audits/([a-f0-9]+)$", self.api_get_audit),
            ("PATCH", r"^/api/audits/([a-f0-9]+)$", self.api_update_audit),
            ("DELETE", r"^/api/audits/([a-f0-9]+)$", self.api_delete_audit),
            ("POST", r"^/api/audits/([a-f0-9]+)/clone$", self.api_clone_audit),
            ("GET", r"^/api/audits/([a-f0-9]+)/criteria$", self.api_criteria),
            ("GET", r"^/api/audits/([a-f0-9]+)/score$", self.api_score),
            ("PUT", r"^/api/audits/([a-f0-9]+)/items/([^/]+)$", self.api_upsert_item),
            ("POST", r"^/api/audits/([a-f0-9]+)/items/([^/]+)/evidence$", self.api_upload_evidence),
            ("POST", r"^/api/audits/([a-f0-9]+)/items/([^/]+)/evidence/url$", self.api_add_url),
            ("PATCH", r"^/api/evidence/([a-f0-9]+)$", self.api_update_evidence),
            ("DELETE", r"^/api/evidence/([a-f0-9]+)$", self.api_delete_evidence),
            ("GET", r"^/api/audits/([a-f0-9]+)/evidence/([a-f0-9]+)/file$", self.api_evidence_file),
            ("GET", r"^/api/audits/([a-f0-9]+)/export/zip$", self.api_export_zip),
            ("GET", r"^/api/audits/([a-f0-9]+)/export/book$", self.api_export_book),
        ]
        for m, pattern, func in routes:
            if m != method:
                continue
            match = re.match(pattern, path)
            if match:
                try:
                    return func(match, query)
                except ValueError as e:
                    return self._send_error(400, str(e))
                except FileNotFoundError as e:
                    return self._send_error(404, str(e))
        return self._send_error(404, "route inconnue: " + path)

    def api_meta(self, match, query):
        self._send_json({
            "statuses": STATUSES,
            "status_labels": {
                "TODO": "À traiter", "IN_PROGRESS": "En cours",
                "EVIDENCE_MISSING": "Preuve manquante",
                "NON_COMPLIANT": "Non conforme (action requise)",
                "VALIDATED": "Validé (prêt pour audit)",
            },
            "types": ["camping", "prl"],
            "mentions": ["tourisme", "loisirs"],
            "star_carte_thresholds": scoring.STAR_CARTE_THRESHOLDS,
            "obligatory_ratio": scoring.OBLIGATORY_RATIO,
            "compensation_factor": scoring.COMPENSATION_FACTOR,
            "profile_fields": [
                {"key": "nb_emplacements", "label": "Nombre total d'emplacements", "type": "number"},
                {"key": "nb_emplacements_hll_rml", "label": "Emplacements HLL / RML", "type": "number"},
                {"key": "nb_emplacements_caravanes", "label": "Emplacements caravanes / camping-cars", "type": "number"},
                {"key": "nb_emplacements_locatifs", "label": "Emplacements avec hébergement locatif", "type": "number"},
                {"key": "has_pool", "label": "Piscine", "type": "bool"},
                {"key": "has_restaurant", "label": "Restaurant sur place", "type": "bool"},
                {"key": "has_bar", "label": "Bar / point de restauration", "type": "bool"},
                {"key": "has_locatifs", "label": "Hébergements locatifs (HLL/RML)", "type": "bool"},
                {"key": "has_aire_autocaravane", "label": "Aire de stationnement autocaravanes", "type": "bool"},
                {"key": "wifi_sans_positionnement", "label": "Positionnement commercial « sans Wifi »", "type": "bool"},
                {"key": "adults_only", "label": "Positionnement « adultes uniquement »", "type": "bool"},
                {"key": "naturiste", "label": "Positionnement naturiste", "type": "bool"},
                {"key": "ecologique", "label": "Positionnement écologique", "type": "bool"},
                {"key": "saisonnier", "label": "Ouverture saisonnière", "type": "bool"},
            ],
        })

    def api_referentiel(self, match, query):
        self._send_json(load_ref())

    def api_ref_stats(self, match, query):
        self._send_json(ref_stats(load_ref()))

    def api_list_audits(self, match, query):
        self._send_json({"audits": db.list_audits()})

    def api_create_audit(self, match, query):
        body = self._json_body()
        name = (body.get("name") or "").strip()
        if not name:
            return self._send_error(400, "name requis")
        audit = db.create_audit(
            name,
            body.get("type", "camping"),
            body.get("mention", "tourisme"),
            body.get("target_stars", 3),
            body.get("profile", {}),
        )
        self._send_json({"audit": audit}, 201)

    def _get_audit_or_404(self, aid):
        audit = db.get_audit(aid)
        if not audit:
            raise FileNotFoundError("dossier introuvable")
        return audit

    def api_get_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        items = db.list_items(audit["id"])
        evs = db.list_evidences(audit["id"])
        self._send_json({"audit": audit, "items": items, "evidences": evs})

    def api_update_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        body = self._json_body()
        updated = db.update_audit(audit["id"], body)
        self._send_json({"audit": updated})

    def api_delete_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        db.delete_audit(audit["id"])
        shutil.rmtree(os.path.join(DATA_DIR, "dossiers", audit["id"]), ignore_errors=True)
        self._send_json({"deleted": audit["id"]})

    def api_clone_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        body = self._json_body()
        new_name = (body.get("name") or f"{audit['name']} — copie").strip()
        new = db.clone_audit(audit["id"], new_name)
        src_dir = os.path.join(DATA_DIR, "dossiers", audit["id"], "evidences")
        dst_dir = os.path.join(DATA_DIR, "dossiers", new["id"], "evidences")
        if os.path.isdir(src_dir):
            shutil.copytree(src_dir, dst_dir)
        self._send_json({"audit": new}, 201)

    def _profile_of(self, audit):
        return {**audit.get("profile", {}), "type": audit["type"], "mention": audit["mention"]}

    def api_criteria(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = load_ref()
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        idx = criteria_index(ref)
        items = db.list_items(audit["id"])
        evs = db.list_evidences(audit["id"])
        ev_count = {}
        for e in evs:
            ev_count[e["criterion_id"]] = ev_count.get(e["criterion_id"], 0) + 1
        appl = {a["id"]: a for a in scoring.applicable_criteria(ref, profile, stars)}
        out = []
        for c in ref.get("criteria", []):
            a = appl.get(c["id"], {"code": "NA", "points": 0, "ajo": False})
            it = items.get(c["id"], {})
            out.append({
                "id": c["id"], "chapter": c.get("chapter"), "section": c.get("section"),
                "title": c.get("title"), "precisions": c.get("precisions", ""),
                "rules": c.get("rules", {}), "evidence_types": c.get("evidence_types", ["PHOTO", "PDF"]),
                "code": a["code"], "points": a["points"], "ajo": a["ajo"],
                "status": it.get("status", "TODO"), "notes": it.get("notes", ""),
                "validated_by": it.get("validated_by", ""), "validated_at": it.get("validated_at"),
                "nb_evidences": ev_count.get(c["id"], 0),
                "validated_ref": c.get("validated", False),
            })
        self._send_json({"audit": audit, "stars": stars, "chapters": ref.get("chapters", []), "criteria": out})

    def api_score(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = load_ref()
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        items = db.list_items(audit["id"])
        statuses = {cid: {"status": it["status"]} for cid, it in items.items()}
        score = scoring.compute_scores(ref, profile, stars, statuses)
        reachable = scoring.reachable_stars(ref, profile, statuses)
        self._send_json({"score": score, "reachable": reachable, "stars": stars})

    def api_upsert_item(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        ref = load_ref()
        idx = criteria_index(ref)
        if cid not in idx:
            return self._send_error(404, "critère inconnu")
        body = self._json_body()
        status = body.get("status", "TODO")
        if status not in STATUSES:
            return self._send_error(400, "statut invalide")
        profile = self._profile_of(audit)
        crit = idx[cid]
        if status == "VALIDATED" and scoring.is_ajo(crit, profile):
            if not db.list_evidences(audit["id"], cid):
                return self._send_error(422, "Critère AJO : au moins une preuve (photo, PDF ou URL) est requise avant validation")
        item = db.upsert_item(audit["id"], cid, status, body.get("notes", ""), body.get("validated_by", ""))
        self._send_json({"item": dict(item)})

    def api_upload_evidence(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        ref = load_ref()
        if cid not in criteria_index(ref):
            return self._send_error(404, "critère inconnu")
        parts = parse_multipart(self._body(), self.headers.get("Content-Type", ""))
        captions = {}
        files = []
        for p in parts:
            if p["name"] == "captions":
                try:
                    captions = json.loads(p["data"].decode("utf-8"))
                except Exception:
                    captions = {}
            elif p["filename"]:
                files.append(p)
        if not files:
            return self._send_error(400, "aucun fichier reçu")
        ev_dir = os.path.join(DATA_DIR, "dossiers", audit["id"], "evidences", cid)
        os.makedirs(ev_dir, exist_ok=True)
        existing = db.list_evidences(audit["id"], cid)
        seq = len(existing)
        created = []
        for p in files:
            seq += 1
            fname = safe_filename(cid, seq, p["filename"])
            with open(os.path.join(ev_dir, fname), "wb") as f:
                f.write(p["data"])
            kind = evidence_kind(p["filename"])
            ev = db.add_evidence(audit["id"], cid, kind, fname, original_name=p["filename"],
                                 caption=captions.get(p["filename"], ""))
            created.append(ev)
        self._send_json({"evidences": created}, 201)

    def api_add_url(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        body = self._json_body()
        url = (body.get("url") or "").strip()
        if not url:
            return self._send_error(400, "url requise")
        ev = db.add_evidence(audit["id"], cid, "URL", "", original_name=url, url=url, caption=body.get("caption", ""))
        self._send_json({"evidence": ev}, 201)

    def api_update_evidence(self, match, query):
        ev = db.update_evidence(match.group(1), caption=self._json_body().get("caption"),
                                stale=self._json_body().get("stale"))
        if not ev:
            return self._send_error(404, "preuve introuvable")
        self._send_json({"evidence": ev})

    def api_delete_evidence(self, match, query):
        ev = db.get_evidence(match.group(1))
        if not ev:
            return self._send_error(404, "preuve introuvable")
        path = os.path.join(DATA_DIR, "dossiers", ev["audit_id"], "evidences", ev["criterion_id"], ev["filename"])
        if ev["filename"] and os.path.exists(path):
            os.remove(path)
        db.delete_evidence(ev["id"])
        self._send_json({"deleted": ev["id"]})

    def api_evidence_file(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ev = db.get_evidence(match.group(2))
        if not ev or ev["audit_id"] != audit["id"]:
            return self._send_error(404, "preuve introuvable")
        if ev["kind"] == "URL":
            self.send_response(302)
            self.send_header("Location", ev["url"])
            self.end_headers()
            return
        path = os.path.join(DATA_DIR, "dossiers", audit["id"], "evidences", ev["criterion_id"], ev["filename"])
        if not os.path.exists(path):
            return self._send_error(404, "fichier introuvable")
        ext = os.path.splitext(ev["filename"])[1].lower()
        self._send_file(path, CONTENT_TYPES.get(ext, "application/octet-stream"))

    def api_export_zip(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = load_ref()
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        items = db.list_items(audit["id"])
        statuses = {cid: {"status": it["status"]} for cid, it in items.items()}
        score = scoring.compute_scores(ref, profile, stars, statuses)
        evs = db.list_evidences(audit["id"])
        zip_path = build_zip(audit, ref, items, evs, score, DATA_DIR, EXPORT_DIR)
        self._send_file(zip_path, "application/zip", download_name=os.path.basename(zip_path))

    def api_export_book(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = load_ref()
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        items = db.list_items(audit["id"])
        statuses = {cid: {"status": it["status"]} for cid, it in items.items()}
        score = scoring.compute_scores(ref, profile, stars, statuses)
        evs = db.list_evidences(audit["id"])
        book = build_book_html(audit, ref, items, evs, score, link_base="")
        body = book.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv=None):
    argv = argv or sys.argv[1:]
    host = "127.0.0.1"
    port = 8000
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "dossiers"), exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Prépa Classement Camping/PRL — http://{host}:{port} (Ctrl+C pour arrêter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
