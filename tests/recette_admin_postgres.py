"""Exercise the separate web administration in the parent's disposable PostgreSQL cluster."""
import base64
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    host = "gestion.example.test"
    os.environ.update(DJANGO_SETTINGS_MODULE="administration.settings", HPA_SUPABASE_ROLE="webadmin", HPA_ADMIN_HOST=host)
    from administration import settings
    settings.DATABASES["default"].update(HOST="127.0.0.1", PORT=int(os.environ["HPA_TEST_PG_PORT"]),
                                         USER="hpa_rating_webadmin", TIME_ZONE="GMT", OPTIONS={"sslmode": "disable"})
    import django
    django.setup()
    from django.test import Client
    from django_otp.oath import totp
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
    assert post("/api/admin/setup/start",{"ticket":"intrus","password":"Test indépendant du camping 32"}).status_code == 403
    start = post("/api/admin/setup/start",{"ticket":ticket,"password":"Test indépendant du camping 32"}).json()
    otp = str(totp(base64.b32decode(start["manual_key"]))).zfill(6)
    result = post("/api/admin/setup/finish",{"otp":otp}).json()
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
    assert post(path,{}).status_code == 409
    assert post("/api/logout/admin",{}).status_code == 200
    assert client.get("/api/session",secure=True).json() == {"admin":False,"setup_required":False}
    assert post("/api/admin/login",{"password":"Test indépendant du camping 32","otp":result["recovery_codes"][0]}).status_code == 200
    print("Administration HTTPS : activation privée, TOTP, demande, invitation unique, déconnexion et récupération vérifiés.")


if __name__ == "__main__":
    run()
