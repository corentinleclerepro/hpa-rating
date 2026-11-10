import re
import shutil
from pathlib import Path
from django.conf import settings
from django.urls import path, re_path
from . import access, demo, landing
from .access import guest_from
from hpa_shared.http import endpoint, error
from hpa_shared.webfiles import frontend
from .server import DossierAPI
from .storage import store

page, asset = frontend(Path(__file__).parent / "static", (
    "app.js", "style.css", "dossier.png", "workspace.js", "guide.js", "reference.js", "access.js", "ui.js", "camping.jpg",
    "landing.css", "landing.js", "clairiere.jpg", "preparation.jpg", "apercu-dossier.jpg"))


AID = r"audits/([0-9a-f]+)"
CID = AID + r"/items/([0-9]+)"
ROUTES = [
    ("meta", {"GET":"meta"}), ("referentiel", {"GET":"referentiel"}), ("referentiel/stats", {"GET":"ref_stats"}),
    ("audits", {"GET":"list_audits", "POST":"create_audit"}), ("audits/demo", {"POST":"demo"}),
    (AID, {"GET":"get_audit","PATCH":"update_audit","DELETE":"delete_audit"}),
    (AID+"/clone", {"POST":"clone_audit"}), (AID+"/resume", {"PUT":"resume"}),
    (AID+"/review-proofs", {"POST":"review_proofs"}),
    (AID+"/criteria", {"GET":"criteria"}), (AID+"/score", {"GET":"score"}), (CID, {"PUT":"upsert_item"}),
    (CID+"/evidence", {"POST":"upload_evidence"}), (CID+"/evidence/url", {"POST":"add_url"}),
    (CID+"/evidence/transfers", {"POST":"evidence_transfer"}),
    (CID+"/evidence/transfers/complete", {"POST":"evidence_transfer"}),
    (CID+r"/evidence/transfers/([0-9a-f]{32})/([0-9]{1,2})", {"PUT":"evidence_transfer"}),
    (r"evidence/([0-9a-f]+)", {"PATCH":"update_evidence","DELETE":"delete_evidence"}),
    (AID+r"/evidence/([0-9a-f]+)/file", {"GET":"evidence_file"}),
    (AID+"/export/zip", {"GET":"export_zip"}), (AID+"/export/book", {"GET":"export_book"}),
]


@endpoint(["GET","POST","PATCH","PUT","DELETE"])
def domain(request, resource):
    guest = guest_from(request)
    if not guest:
        return error("Saisissez votre code personnel pour ouvrir votre espace.", 401)
    db = store()
    with db.lock:
        for pattern, methods in ROUTES:
            match = re.fullmatch(pattern, resource)
            if not match:
                continue
            if request.method not in methods:
                return error("Méthode non autorisée.", 405)
            if int(request.META.get("CONTENT_LENGTH") or 0) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                return error("Envoyez au maximum 64 Mo à la fois.", 413)
            api = DossierAPI(request, db, guest["id"])
            handler = getattr(api, "api_" + methods[request.method])
            query = dict(request.GET.lists())
            if request.method == "GET":
                return handler(match, query)
            try:
                with db.atomic(guest["id"]):
                    response = handler(match, query)
            except BaseException:
                for source, dest in reversed(api.staged):
                    dest.rename(source)
                raise
            for _, dest in api.staged:
                shutil.rmtree(dest)
            return response
        return error("Ressource introuvable.", 404)


# Only declared dossier routes are exposed; unknown APIs never enter guest authentication.
resources = "|".join(pattern for pattern, _methods in ROUTES)
urlpatterns = [
    path("", landing.home), path("cgu", landing.information, {"page": "terms"}, name="terms"),
    path("mentions-legales", landing.information, {"page": "legal"}),
    path("confidentialite", landing.information, {"page": "privacy"}), path("demande-acces", landing.request_access),
    path("demo", demo.demo), path("demo/justificatifs/<str:name>", demo.proof),
    path("robots.txt", landing.robots), path("sitemap.xml", landing.sitemap),
    path("connexion", landing.connection), path("espace", page), path("static/<str:name>", asset),
    path("api/session", access.session_info), path("api/login", access.guest_login), path("api/logout/guest", access.guest_logout),
    re_path(r"^api/(?P<resource>" + resources + r")$", domain),
]
