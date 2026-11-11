"""Exercise the separate web administration in the parent's disposable PostgreSQL cluster."""
import os
import re
from pathlib import Path
import sys
from unittest.mock import patch
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    host = "gestion.example.test"
    os.environ.update(DJANGO_SETTINGS_MODULE="administration.settings", HPA_SUPABASE_ROLE="webadmin", HPA_ADMIN_HOST=host)
    from administration import settings
    settings.ADMIN_EMAIL = "operator@example.invalid"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DATABASES["default"].update(HOST="127.0.0.1", PORT=int(os.environ["HPA_TEST_PG_PORT"]),
                                         USER="hpa_rating_webadmin", TIME_ZONE="GMT", OPTIONS={"sslmode": "disable"})
    import django
    django.setup()
    from django.test import Client
    from django.core import mail
    from deploy.prepare_admin import prepare_admin
    client = Client(enforce_csrf_checks=True, HTTP_HOST=host, REMOTE_ADDR="203.0.113.3")
    with TemporaryDirectory() as directory:
        file = Path(directory)/"activation.txt"
        assert prepare_admin(file)
        ticket = file.read_text("utf-8").split("utilisable une fois\n")[1].splitlines()[0]
    def post(path, data):
        return client.post(path, data, content_type="application/json", secure=True,
                           HTTP_ORIGIN="https://"+host, HTTP_X_CSRFTOKEN=client.cookies["hpa_console_csrf"].value)
    assert client.get("/api/session",secure=True).json() == {"admin":False,"setup_required":True}
    assert client.get("/api/admin/demandes",secure=True).status_code == 403
    assert client.get("/api/admin/parcours",secure=True).status_code == 403
    assert post("/api/admin/setup/start",{"ticket":"intrus","password":"Test indépendant du camping 32"}).status_code == 403
    start = post("/api/admin/setup/start",{"ticket":ticket,"password":"Test indépendant du camping 32"}).json()
    assert start == {"email_pending":"setup","expires_in":600}
    code = re.search(r"^([0-9]{6})$",mail.outbox[-1].body,re.MULTILINE)[1]
    result = post("/api/admin/setup/finish",{"code":code}).json()
    assert len(result["recovery_codes"]) == 8
    assert client.get("/api/audits",secure=True).status_code == 404
    listing = "/api/admin/demandes"
    pending = client.get(listing,secure=True).json()["requests"]
    refused = next(row for row in pending if row["email"] == "refus@example.test")
    assert post(listing+"/"+refused["id"]+"/decline", {}).status_code == 200
    remaining = client.get(listing,secure=True).json()["requests"]
    assert all(row["id"] != refused["id"] and row["email"] != refused["email"] for row in remaining)
    entry = next(row for row in remaining if row["email"] == "test@example.test")
    assert entry["status"] == "pending" and entry["camping"] == "Test postal"
    path = "/api/admin/demandes/" + entry["id"] + "/approve"
    invitation = post(path,{}).json()
    assert invitation["code"].startswith("HPA-") and invitation["email"] == "test@example.test"
    Path(os.environ["HPA_TEST_INVITATION"]).write_text(invitation["code"], encoding="ascii")
    assert client.get("/api/admin/parcours",secure=True).json() == {"home":0,"start":0,"request":3,"continued":0}
    assert post(path,{}).status_code == 409
    assert post("/api/logout/admin",{}).status_code == 200
    assert client.get("/api/session",secure=True).json() == {"admin":False,"setup_required":False}
    with patch("administration.email_codes.send_mail", side_effect=OSError("test transport")):
        assert post("/api/admin/login",{"password":"Test indépendant du camping 32"}).status_code == 503
    assert client.get("/api/session",secure=True).json()["admin"] is False
    assert post("/api/admin/login",{"password":"Test indépendant du camping 32"}).json()["email_pending"] == "login"
    assert client.get("/api/admin/demandes",secure=True).status_code == 403
    assert mail.outbox[-1].to == ["operator@example.invalid"]
    code = re.search(r"^([0-9]{6})$",mail.outbox[-1].body,re.MULTILINE)[1]
    assert post("/api/admin/login/confirm",{"code":code}).status_code == 200
    assert post("/api/logout/admin",{}).status_code == 200
    assert post("/api/admin/login",{"password":"Test indépendant du camping 32","recovery":result["recovery_codes"][0]}).status_code == 200
    print("Administration HTTPS : activation, code par e-mail, invitations et récupération vérifiés.")


if __name__ == "__main__":
    run()
