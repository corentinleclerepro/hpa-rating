"""The first three applicable sheets, saved locally or handed to an invited owner."""
import json
import re
from functools import lru_cache

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_safe
from hpa_shared.http import endpoint, error, payload
from hpa_shared.registry import count_starter, registry
from . import workflow
from .db import STATUSES
from .exporters import STATUS_LABELS
from .referentiel import CURRENT_VERSION, load, criteria_index
from .scoring import applicable_criteria


def first_rows(terrain, mention, stars, pitches=None):
    ref = load()
    profile = {"type": terrain, "mention": mention, "nb_emplacements": pitches}
    groups = workflow.ordered_groups(ref, applicable_criteria(ref, profile, stars))
    return (groups["prerequisites"] + groups["criteria"])[:3]


@lru_cache(maxsize=1)
def public_grid():
    paths, sheets = {}, {}
    official = criteria_index(load())
    for terrain in ("camping", "prl"):
        for mention in ("tourisme", "loisirs"):
            for stars in range(1, 6):
                rows = first_rows(terrain, mention, stars)
                paths[f"{terrain}/{mention}/{stars}"] = [
                    {"id": row["id"], "proof": row["ajo"], "points": row["points"]} for row in rows]
                for row in rows:
                    sheets[row["id"]] = official[row["id"]]["title"]
    return {"reference": CURRENT_VERSION, "paths": paths, "sheets": sheets}


def checked_draft(draft):
    if not isinstance(draft, dict) or set(draft) != {"id","reference","type","mention","stars","pitches","answers"}:
        raise ValueError("Le brouillon est incomplet. Revenez au profil et enregistrez-le.")
    if not isinstance(draft["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", draft["id"]):
        raise ValueError("Identifiant de brouillon invalide.")
    if draft["reference"] != CURRENT_VERSION:
        raise ValueError("La grille a changé. Vérifiez les premières fiches avec le référentiel actuel.")
    if draft["type"] not in ("camping","prl") or draft["mention"] not in ("tourisme","loisirs"):
        raise ValueError("Type ou mention de terrain invalide.")
    if type(draft["stars"]) is not int or not 1 <= draft["stars"] <= 5:
        raise ValueError("Choisissez entre 1 et 5 étoiles.")
    if type(draft["pitches"]) is not int or not 1 <= draft["pitches"] <= 1000000:
        raise ValueError("Vérifiez le nombre d’emplacements.")
    rows = first_rows(draft["type"], draft["mention"], draft["stars"], draft["pitches"])
    answers = draft["answers"]
    if not isinstance(answers, dict) or set(answers) != {row["id"] for row in rows[:len(answers)]}:
        raise ValueError("Les réponses doivent suivre les trois premières fiches applicables.")
    for row in rows[:len(answers)]:
        answer = answers[row["id"]]
        if answer not in STATUSES or answer == "TODO" or (row["ajo"] and answer == "VALIDATED"):
            raise ValueError("Vérifiez le statut choisi. Un justificatif obligatoire se joint dans l’espace invité.")
    return draft


@require_safe
def page(request):
    from .landing import public_response
    return public_response(request, "starter.html", {"grid": public_grid(), "csrf_token": get_token(request)})


@endpoint(["POST"])
def public_event(request, event):
    if event not in ("home","start"):
        raise FileNotFoundError
    if int(request.META.get("CONTENT_LENGTH") or 0) or request.body:
        return error("Requête inattendue.")
    db = registry()
    with db.atomic():
        count_starter(db, event)
    return HttpResponse(status=204)


def attach_registry(db):
    # SQLite stores requests and working dossiers in separate files. Attach the registry
    # to the guest connection so consuming a snapshot and creating its dossier commit together.
    if not settings.CLOUD_ROLE and not getattr(db, "has_invites", False):
        registry()
        db.conn.execute("ATTACH DATABASE ? AS invites", (str(settings.REGISTRY_DIR / "invitations.sqlite3"),))
        db.has_invites = True


def approved(db, owner):
    if settings.CLOUD_ROLE:
        return db.conn.execute("SELECT * FROM hpa_rating.approved_starter(?)", (owner,)).fetchone()
    return db.conn.execute("""SELECT s.content,r.camping FROM invites.request_starters s
        JOIN invites.access_requests r ON r.id=s.request_id
        WHERE r.guest_id=? AND r.status='approved'""", (owner,)).fetchone()


def import_draft(db, owner, draft, name):
    prior = db.conn.execute("SELECT audit_id FROM starter_imports WHERE owner_id=? AND draft_id=?",
                            (owner, draft["id"])).fetchone()
    if prior:
        return prior["audit_id"]
    audit = db.create_audit(name, draft["type"], draft["mention"], draft["stars"],
                            {"nb_emplacements": draft["pitches"]}, draft["reference"], owner)
    aid = audit["id"]
    db.conn.execute("UPDATE audits SET profile_confirmed=1 WHERE id=?", (aid,))
    db.log(aid, "Profil repris du mini-dossier.", "profile")
    for cid, answer in sorted(draft["answers"].items(), key=lambda pair: int(pair[0])):
        db.upsert_item(aid, cid, answer, "", "", validated_stars=draft["stars"])
        db.log(aid, f"Critère {cid} · {STATUS_LABELS[answer]} (brouillon repris).", "criteria", cid)
    flow = workflow.progress(db.get_audit(aid), db.list_items(aid))
    db.conn.execute("UPDATE audits SET resume_criterion=? WHERE id=?", (flow["next_id"], aid))
    db.conn.execute("INSERT INTO starter_imports(owner_id,draft_id,audit_id) VALUES(?,?,?)",
                    (owner,draft["id"],aid))
    return aid


def claim(request, db, owner):
    pending = approved(db, owner)
    if request.method == "GET":
        if not pending:
            return JsonResponse({"attached": None})
        draft = json.loads(pending["content"])
        return JsonResponse({"attached": {"id": draft["id"], "name": pending["camping"]}})
    if len(request.body) > 4096:
        return HttpResponse(status=413)
    body = payload(request)
    source = body.get("source")
    if source == "invitation":
        if not pending:
            draft_id = body.get("id")
            if isinstance(draft_id, str):
                prior = db.conn.execute("SELECT audit_id FROM starter_imports WHERE owner_id=? AND draft_id=?",
                                        (owner,draft_id)).fetchone()
                if prior:
                    return JsonResponse({"id": prior["audit_id"], "draft_id": draft_id})
            raise FileNotFoundError
        draft = checked_draft(json.loads(pending["content"]))
        if body.get("id") != draft["id"]:
            return error("Le brouillon proposé a changé. Rechargez votre espace.", 409)
        name = pending["camping"]
    elif source == "local":
        draft = checked_draft(body.get("draft"))
        name = db.conn.execute("SELECT label FROM guests WHERE id=?" if settings.CLOUD_ROLE else
                               "SELECT label FROM invites.guests WHERE id=?", (owner,)).fetchone()["label"]
        if pending and json.loads(pending["content"])["id"] == draft["id"]:
            name = pending["camping"]
    else:
        return error("Choisissez le brouillon à reprendre.")
    aid = import_draft(db, owner, draft, name)
    if pending and json.loads(pending["content"])["id"] == draft["id"]:
        if settings.CLOUD_ROLE:
            db.conn.execute("SELECT hpa_rating.clear_approved_starter(?)", (owner,))
        else:
            db.conn.execute("""DELETE FROM invites.request_starters WHERE request_id IN
                (SELECT id FROM invites.access_requests WHERE status='approved' AND guest_id=?)""", (owner,))
    return JsonResponse({"id": aid, "draft_id": draft["id"]})


def count_continuation(db, aid):
    updated = db.conn.execute("UPDATE starter_imports SET continued=1 WHERE audit_id=? AND continued=0", (aid,))
    if updated.rowcount:
        count_starter(db, "continued", attached=True)
