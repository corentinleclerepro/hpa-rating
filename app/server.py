"""Private dossier API. Django handles sessions, request parsing and CSRF."""
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import uuid
from email import policy
from email.parser import BytesParser
from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, JsonResponse
from . import scoring, workflow
from .db import STATUSES
from .exporters import STATUS_LABELS, build_book_html, build_zip, evidence_kind, safe_filename
from hpa_shared.http import error, payload
from .profile import PROFILE_FIELDS
from .referentiel import criteria_index, for_audit, load as load_ref, stats as ref_stats
from .storage import sample_audit, store

CONTENT_TYPES = {".pdf":"application/pdf", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".png":"image/png",
                 ".gif":"image/gif", ".webp":"image/webp", ".heic":"image/heic"}


def checked_profile(body):
    if "name" in body and (not isinstance(body["name"], str) or not 1 <= len(body["name"].strip()) <= 180):
        raise ValueError("Le nom doit contenir entre 1 et 180 caractères.")
    if "name" in body:
        body["name"] = body["name"].strip()
    if body.get("type","camping") not in ("camping","prl") or body.get("mention","tourisme") not in ("tourisme","loisirs"):
        raise ValueError("Type d’établissement ou mention invalide.")
    stars = body.get("target_stars",3)
    if type(stars) != int or stars not in range(1,6):
        raise ValueError("Choisissez de 1 à 5 étoiles.")
    profile = body.get("profile", {})
    if not isinstance(profile, dict):
        raise ValueError("Profil invalide.")
    for field in PROFILE_FIELDS:
        value = profile.get(field["key"])
        if value is None:
            continue
        if field["type"] == "bool" and type(value) != bool:
            raise ValueError(field["label"] + " : indiquez oui ou non.")
        if field["type"] == "number" and (type(value) != int or value < 0):
            raise ValueError(field["label"] + " : indiquez un nombre entier positif ou nul.")
    return body


class DossierAPI:
    def __init__(self, request, db, owner):
        self.request, self.db, self.owner = request, db, owner
        self.staged = []

    def failure(self, status, message):
        return error(message, status)

    def summary(self, audit, items=None):
        items = self.db.list_items(audit["id"]) if items is None else items
        rows = scoring.applicable_criteria(for_audit(audit), self._profile_of(audit), audit["target_stars"], items)
        active = [row for row in rows if row["code"] != "NA"]
        last = self.db.conn.execute("SELECT message,created_at FROM activity WHERE audit_id=? ORDER BY id DESC LIMIT 1", (audit["id"],)).fetchone()
        return {**audit, "applicable":len(active), "filled":sum(r["status"] != "TODO" for r in active),
                "workflow": workflow.progress(audit, items, rows),
                "last_event": dict(last) if last else None}

    def guide(self, audit):
        return workflow.progress(audit, self.db.list_items(audit["id"]))

    def criterion_lock(self, audit, cid, *, piece=False):
        flow = self.guide(audit)
        if cid in flow["allowed_ids"] or (piece and "proofs" in flow["open_steps"]):
            return None
        return self.failure(409, workflow.explain(flow) if flow["current"] != "summary" else
                            "Ce critère ne s’applique pas au profil et à la catégorie visée.")

    def summary_lock(self, audit):
        flow = self.guide(audit)
        if flow["current"] != "summary":
            return self.failure(409, workflow.explain(flow))

    def revisit_proofs(self, aid):
        self.db.conn.execute("UPDATE audits SET proofs_reviewed=0 WHERE id=? AND proofs_reviewed<>0", (aid,))

    def stage_deletion(self, aid):
        if not re.fullmatch(r"[0-9a-f]+", aid):
            raise ValueError("Dossier invalide.")
        if settings.CLOUD_ROLE:
            return  # PostgreSQL removes file chunks in the same transaction as the dossier.
        for kind in ("dossiers", "exports"):
            source = settings.DATA_DIR / kind / aid
            if source.is_dir():
                private = settings.DATA_DIR / ".removed"
                private.mkdir(exist_ok=True)
                dest = private / f"{kind}-{aid}-{uuid.uuid4().hex}"
                source.rename(dest)
                self.staged.append((source, dest))

    def api_demo(self, match, query):
        audit = sample_audit(self.db, self.owner)
        return JsonResponse({"audit":audit}, status=201)

    def api_resume(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        body = payload(self.request)
        cid = str(body.get("criterion_id",""))
        if body.get("stars", audit["target_stars"]) != audit["target_stars"]:
            return JsonResponse({"saved":False})
        if cid not in criteria_index(for_audit(audit)):
            raise ValueError("Critère inconnu.")
        if (locked := self.criterion_lock(audit, cid)) is not None:
            return locked
        self.db.conn.execute("UPDATE audits SET resume_criterion=? WHERE id=?", (cid, audit["id"]))
        return JsonResponse({"saved":True})


    def api_meta(self, match, query):
        return JsonResponse({
            "chunked_upload": bool(settings.CLOUD_ROLE),
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
            "profile_fields": PROFILE_FIELDS,
        })

    def api_referentiel(self, match, query):
        return JsonResponse(load_ref())

    def api_ref_stats(self, match, query):
        return JsonResponse(ref_stats(load_ref()))

    def api_list_audits(self, match, query):
        return JsonResponse({"audits": [self.summary(a) for a in self.db.list_audits(self.owner)]})

    def api_create_audit(self, match, query):
        body = checked_profile(payload(self.request))
        name = (body.get("name") or "").strip()
        if not name:
            return self.failure(400, "name requis")
        audit = self.db.create_audit(
            name,
            body.get("type", "camping"),
            body.get("mention", "tourisme"),
            body.get("target_stars", 3),
            body.get("profile", {}), owner=self.owner,
        )
        self.db.log(audit["id"], "Dossier créé.", "profile")
        return JsonResponse({"audit": audit}, status=201)

    def _get_audit_or_404(self, aid):
        audit = self.db.get_audit(aid)
        if not audit or audit["owner_id"] != self.owner:
            raise FileNotFoundError("dossier introuvable")
        return audit

    def api_get_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        items = self.db.list_items(audit["id"])
        evs = self.db.list_evidences(audit["id"])
        info = self.summary(audit, items)
        flow = info["workflow"]
        allowed = set(flow["allowed_ids"])
        return JsonResponse({"audit": info, "items": {k:v for k,v in items.items() if k in allowed},
                             "evidences": [e for e in evs if e["criterion_id"] in allowed or "proofs" in flow["open_steps"]],
                             "evidence_count": len(evs), "history": self.db.history(audit["id"])})

    def api_update_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        body = payload(self.request)
        checked_profile(body)
        confirm = body.pop("confirm_profile", False)
        if type(confirm) is not bool:
            raise ValueError("Confirmation de profil invalide.")
        profile = body.get("profile", audit["profile"])
        if confirm and not workflow.profile_ready(profile):
            return self.failure(422, "Indiquez le nombre total d’emplacements (au moins un) pour confirmer le profil.")
        updated = self.db.update_audit(audit["id"], body)
        confirmed = (confirm or audit["profile_confirmed"]) and workflow.profile_ready(profile)
        self.db.conn.execute("UPDATE audits SET profile_confirmed=? WHERE id=?", (int(confirmed), audit["id"]))
        if any(updated[k] != audit[k] for k in ("type", "mention", "target_stars", "profile")):
            self.revisit_proofs(audit["id"])
        self.db.demote_missing_evidence(audit["id"], [c["id"] for c in for_audit(updated)["criteria"] if scoring.is_ajo(c,self._profile_of(updated))])
        self.db.log(audit["id"], "Profil de l’établissement confirmé." if confirm else "Profil de l’établissement mis à jour.", "profile")
        return JsonResponse({"audit": self.summary(self.db.get_audit(audit["id"]))})

    def api_review_proofs(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        flow = self.guide(audit)
        if "proofs" not in flow["open_steps"]:
            return self.failure(409, workflow.explain(flow))
        if payload(self.request).get("reviewed") is not True:
            return self.failure(422, "Confirmez que vous avez relu les pièces et les éventuels manques.")
        if not audit["proofs_reviewed"]:
            self.db.conn.execute("UPDATE audits SET proofs_reviewed=1 WHERE id=?", (audit["id"],))
            self.db.log(audit["id"], "Revue des justificatifs confirmée. Synthèse disponible.", "proofs")
        return JsonResponse({"workflow": self.guide(self.db.get_audit(audit["id"]))})

    def api_delete_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        if payload(self.request).get("confirm_name") != audit["name"]:
            raise ValueError("Retapez le nom exact du dossier pour le supprimer.")
        self.stage_deletion(audit["id"])
        self.db.delete_audit(audit["id"])
        return JsonResponse({"deleted": audit["id"]})

    def api_clone_audit(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        body = payload(self.request)
        new_name = checked_profile({"name": body.get("name") or f"{audit['name']} — copie"})["name"]
        new = self.db.clone_audit(audit["id"], new_name)
        src_dir = os.path.join(settings.DATA_DIR, "dossiers", audit["id"], "evidences")
        dst_dir = os.path.join(settings.DATA_DIR, "dossiers", new["id"], "evidences")
        if not settings.CLOUD_ROLE and os.path.isdir(src_dir):
            try:
                shutil.copytree(src_dir, dst_dir)
            except OSError:
                self.db.delete_audit(new["id"])
                shutil.rmtree(dst_dir, ignore_errors=True)
                raise
        self.db.log(new["id"], "Dossier créé par duplication.", "profile")
        return JsonResponse({"audit": new}, status=201)

    def _profile_of(self, audit):
        return {**audit.get("profile", {}), "type": audit["type"], "mention": audit["mention"]}

    def api_criteria(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = for_audit(audit)
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        if stars != audit["target_stars"] and (locked := self.summary_lock(audit)) is not None:
            return locked
        profile = self._profile_of(audit)
        items = self.db.list_items(audit["id"])
        flow = workflow.progress(audit, items)
        allowed = set(flow["allowed_ids"])
        evs = self.db.list_evidences(audit["id"])
        ev_count = {}
        for e in evs:
            ev_count[e["criterion_id"]] = ev_count.get(e["criterion_id"], 0) + 1
        appl = {a["id"]: a for a in scoring.applicable_criteria(ref, profile, stars, items)}
        out = []
        for c in ref.get("criteria", []):
            a = appl.get(c["id"], {"code": "NA", "points": 0, "ajo": False})
            it = items.get(c["id"], {}) if c["id"] in allowed or "proofs" in flow["open_steps"] else {}
            out.append({
                "id": c["id"], "chapter": c.get("chapter"), "section": c.get("section"),
                "title": c.get("title"), "precisions": c.get("precisions", ""),
                "rules": c.get("rules", {}), "evidence_types": c.get("evidence_types", ["PHOTO", "PDF"]),
                "code": a["code"], "points": a["points"], "ajo": a["ajo"],
                "status": a["status"], "via": a.get("via"), "notes": it.get("notes", ""),
                "exigence": c.get("rules", {}).get(str(stars), {}).get("exigence", ""),
                "source_page": c.get("source_page"), "points_min": c.get("points_min"),
                "awarded_points": it.get("awarded_points"), "validated_stars": it.get("validated_stars"),
                "validated_by": it.get("validated_by", ""), "validated_at": it.get("validated_at"),
                "nb_evidences": ev_count.get(c["id"], 0),
                "validated_ref": c.get("validated", False),
            })
        return JsonResponse({"audit": audit, "stars": stars, "chapters": ref.get("chapters", []), "criteria": out})

    def api_score(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ref = for_audit(audit)
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        if stars != audit["target_stars"] and (locked := self.summary_lock(audit)) is not None:
            return locked
        profile = self._profile_of(audit)
        items = self.db.list_items(audit["id"])
        score = scoring.compute_scores(ref, profile, stars, items)
        if workflow.progress(audit, items)["current"] != "summary":
            return JsonResponse({"score": {"x": {k:score["x"][k] for k in ("obtained", "total")},
                                            "o": {k:score["o"][k] for k in ("obtained", "required", "base_required")}},
                                 "stars": stars, "reachable": None})
        reachable = scoring.reachable_stars(ref, profile, items)
        return JsonResponse({"score": score, "reachable": reachable, "stars": stars})

    def api_upsert_item(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        ref = for_audit(audit)
        idx = criteria_index(ref)
        if cid not in idx:
            return self.failure(404, "critère inconnu")
        if (locked := self.criterion_lock(audit, cid)) is not None:
            return locked
        body = payload(self.request)
        status = body.get("status", "TODO")
        if status not in STATUSES:
            return self.failure(400, "statut invalide")
        if body.get("advance") and status == "TODO":
            return self.failure(422, "Choisissez un statut autre que « À traiter » pour continuer. Vous pouvez aussi enregistrer un brouillon.")
        for key, limit in (("notes", 30000), ("validated_by", 160)):
            if not isinstance(body.get(key, ""), str) or len(body.get(key, "")) > limit:
                raise ValueError("Le texte saisi est invalide ou trop long.")
        profile = self._profile_of(audit)
        crit = idx[cid]
        if status == "VALIDATED" and scoring.is_ajo(crit, profile):
            if not self.db.list_evidences(audit["id"], cid):
                return self.failure(422, "Critère AJO : au moins une preuve (photo, PDF ou URL) est requise avant validation")
        stars = body.get("stars", audit["target_stars"])
        if type(stars) is not int or stars not in range(1, 6):
            raise ValueError("Catégorie invalide")
        if stars != audit["target_stars"]:
            return self.failure(409, "La simulation ne modifie pas le dossier dans la catégorie visée.")
        points = body.get("awarded_points")
        if crit.get("points_min"):
            limit = crit["rules"][str(stars)]["points"]
            if points is not None or status == "VALIDATED":
                if type(points) is not int or not crit["points_min"] <= points <= limit:
                    raise ValueError(f"Indiquez la bonification obtenue, entre 1 et {limit} points")
        else:
            points = None
        item = self.db.upsert_item(audit["id"], cid, status, body.get("notes", ""), body.get("validated_by", ""), points, stars)
        self.revisit_proofs(audit["id"])
        self.db.log(audit["id"], f"Critère {cid} · {STATUS_LABELS[status]}.", "criteria", cid)
        return JsonResponse({"item": dict(item), "workflow": self.guide(self.db.get_audit(audit["id"]))})

    def api_upload_evidence(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        ref = for_audit(audit)
        if cid not in criteria_index(ref):
            return self.failure(404, "critère inconnu")
        if (locked := self.criterion_lock(audit, cid, piece=True)) is not None:
            return locked
        mime_header = self.request.headers.get("Content-Type", "")
        if "\r" in mime_header or "\n" in mime_header:
            raise ValueError("Envoi multipart invalide.")
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + mime_header + "\r\n\r\n").encode("latin1") + self.request.evidence_mime)
        if message.get_content_type() != "multipart/form-data" or not message.is_multipart():
            raise ValueError("Envoi multipart invalide.")
        captions, files = {}, []
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            field = part.get_param("name", header="content-disposition")
            if field == "captions":
                captions = json.loads(part.get_payload(decode=True))
            elif field == "files" and part.get_filename():
                original = part.get_filename().replace("\\", "/").rsplit("/", 1)[-1]
                files.append((original, part.get_payload(decode=True)))
        if not files:
            return self.failure(400, "aucun fichier reçu")
        if not isinstance(captions, dict) or not all(isinstance(v, str) for v in captions.values()):
            raise ValueError("Légendes invalides")
        if settings.CLOUD_ROLE:
            from . import cloudfiles
            created = [cloudfiles.register(self.db, audit["id"], cid, cloudfiles.save_bytes(self.db, contents),
                                           original, captions.get(original, "")) for original, contents in files]
            self.revisit_proofs(audit["id"])
            return JsonResponse({"evidences":created}, status=201)
        ev_dir = os.path.join(settings.DATA_DIR, "dossiers", audit["id"], "evidences", cid)
        os.makedirs(ev_dir, exist_ok=True)
        existing = self.db.list_evidences(audit["id"], cid)
        seq = max((int(m.group(1)) for e in existing
                   if (m := re.match(r"^C\d+_(\d+)_", e["filename"]))), default=0)
        paths, records = [], []
        try:
            for original, contents in files:
                while True:
                    seq += 1
                    fname = safe_filename(cid, seq, original)
                    path = os.path.join(ev_dir, fname)
                    try:
                        stream = open(path, "xb")
                        break
                    except FileExistsError:
                        continue
                paths.append(path)
                with stream:
                    stream.write(contents)
                records.append((evidence_kind(original), fname, original, "", captions.get(original, "")))
            created = self.db.add_evidences(audit["id"], cid, records)
        except Exception:
            for path in paths:
                os.remove(path)
            raise
        for proof in created:
            self.db.log(audit["id"], "Justificatif ajouté · " + proof["original_name"], "proofs", cid)
        self.revisit_proofs(audit["id"])
        return JsonResponse({"evidences": created}, status=201)

    def api_add_url(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        cid = match.group(2)
        body = payload(self.request)
        url = (body.get("url") or "").strip()
        if cid not in criteria_index(for_audit(audit)):
            return self.failure(404, "critère inconnu")
        if (locked := self.criterion_lock(audit, cid, piece=True)) is not None:
            return locked
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or any(ord(c) < 32 for c in url):
            return self.failure(400, "Une URL http ou https valide est requise")
        ev = self.db.add_evidence(audit["id"], cid, "URL", "", original_name=url, url=url, caption=body.get("caption", ""))
        self.db.log(audit["id"], "Lien justificatif ajouté.", "proofs", cid)
        self.revisit_proofs(audit["id"])
        return JsonResponse({"evidence": ev}, status=201)

    def api_update_evidence(self, match, query):
        body = payload(self.request)
        if "caption" in body and not isinstance(body["caption"], str):
            raise ValueError("Légende invalide")
        if "stale" in body and body["stale"] not in (0, 1):
            raise ValueError("Marquage invalide")
        previous = self.db.get_evidence(match.group(1))
        if not previous:
            raise FileNotFoundError
        audit = self._get_audit_or_404(previous["audit_id"])
        if (locked := self.criterion_lock(audit, previous["criterion_id"], piece=True)) is not None:
            return locked
        ev = self.db.update_evidence(match.group(1), caption=body.get("caption"), stale=body.get("stale"))
        if not ev:
            return self.failure(404, "preuve introuvable")
        self.db.log(ev["audit_id"], "Justificatif mis à jour · " + (ev["original_name"] or "Lien"), "proofs", ev["criterion_id"])
        self.revisit_proofs(ev["audit_id"])
        return JsonResponse({"evidence": ev})

    def api_delete_evidence(self, match, query):
        ev = self.db.get_evidence(match.group(1))
        if not ev:
            return self.failure(404, "preuve introuvable")
        path = os.path.join(settings.DATA_DIR, "dossiers", ev["audit_id"], "evidences", ev["criterion_id"], ev["filename"])
        audit = self._get_audit_or_404(ev["audit_id"])
        if (locked := self.criterion_lock(audit, ev["criterion_id"], piece=True)) is not None:
            return locked
        criterion = criteria_index(for_audit(audit)).get(ev["criterion_id"], {})
        self.db.delete_evidence(ev, scoring.is_ajo(criterion, self._profile_of(audit)))
        if not settings.CLOUD_ROLE and ev["filename"] and not any(e["filename"] == ev["filename"]
                for e in self.db.list_evidences(ev["audit_id"], ev["criterion_id"])):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        self.db.log(ev["audit_id"], "Justificatif retiré · " + ev["original_name"], "proofs", ev["criterion_id"])
        self.revisit_proofs(ev["audit_id"])
        return JsonResponse({"deleted": ev["id"]})

    def api_evidence_file(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        ev = self.db.get_evidence(match.group(2))
        if not ev or ev["audit_id"] != audit["id"]:
            return self.failure(404, "preuve introuvable")
        if (locked := self.criterion_lock(audit, ev["criterion_id"], piece=True)) is not None:
            return locked
        if ev["kind"] == "URL":
            return HttpResponseRedirect(ev["url"])
        ext = os.path.splitext(ev["filename"])[1].lower()
        mime = CONTENT_TYPES.get(ext, "application/octet-stream")
        if settings.CLOUD_ROLE:
            from .cloudfiles import download
            return download(self.db, ev, mime)
        path = os.path.join(settings.DATA_DIR, "dossiers", audit["id"], "evidences", ev["criterion_id"], ev["filename"])
        if not os.path.exists(path):
            return self.failure(404, "fichier introuvable")
        return FileResponse(open(path, "rb"), content_type=mime, filename=ev["original_name"],
                            as_attachment=mime == "application/octet-stream")

    def api_export_zip(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        if (locked := self.summary_lock(audit)) is not None:
            return locked
        ref = for_audit(audit)
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        items = self.db.list_items(audit["id"])
        score = scoring.compute_scores(ref, profile, stars, items)
        evs = self.db.list_evidences(audit["id"])
        stream = tempfile.TemporaryFile()
        try:
            from .cloudfiles import chunks
            reader = (lambda proof: chunks(self.db, proof["object_key"])) if settings.CLOUD_ROLE else None
            name = build_zip(audit, ref, items, evs, score, settings.DATA_DIR, stream=stream, read_chunks=reader)
            stream.seek(0)
            return FileResponse(stream, as_attachment=True, content_type="application/zip", filename=name)
        except BaseException:
            stream.close()
            raise

    def api_evidence_transfer(self, match, query):
        from . import cloudfiles
        audit = self._get_audit_or_404(match[1])
        cid = match[2]
        if not settings.CLOUD_ROLE or cid not in criteria_index(for_audit(audit)):
            raise FileNotFoundError
        if (locked := self.criterion_lock(audit, cid, piece=True)) is not None:
            return locked
        if self.request.method == "PUT":
            return cloudfiles.put_part(self, audit["id"], cid, match[3], int(match[4]))
        if self.request.path.endswith("/complete"):
            return cloudfiles.finish(self, audit["id"], cid)
        return cloudfiles.prepare(self, audit["id"], cid)

    def api_export_book(self, match, query):
        audit = self._get_audit_or_404(match.group(1))
        if (locked := self.summary_lock(audit)) is not None:
            return locked
        ref = for_audit(audit)
        stars = int(query.get("stars", [audit["target_stars"]])[0])
        profile = self._profile_of(audit)
        items = self.db.list_items(audit["id"])
        score = scoring.compute_scores(ref, profile, stars, items)
        evs = self.db.list_evidences(audit["id"])
        book = build_book_html(audit, ref, items, evs, score, link_base="")
        return HttpResponse(book, content_type="text/html; charset=utf-8")
