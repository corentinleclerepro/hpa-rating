import base64
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from hpa_shared.registry import now_iso, registry, digest, canonical, throttled, limited
from hpa_shared.http import endpoint, error, payload
from . import email_codes
from .state import private_store


def new_code():
    value = base64.b32encode(secrets.token_bytes(15)).decode("ascii")
    return "HPA-" + "-".join(value[i:i+4] for i in range(0, len(value), 4))


def issue_guest(db, label, existing=None):
    label = str(label or "").strip()
    if not label or len(label) > 160:
        raise ValueError("Renseignez un nom ou une adresse e-mail (160 caractères maximum).")
    raw = new_code()
    fingerprint = digest("invite", canonical(raw))
    if existing:
        db.conn.execute("UPDATE guests SET digest=?,version=version+1,revoked=0,code_used=0 WHERE id=?", (fingerprint, existing))
        return existing, raw
    gid = uuid.uuid4().hex
    db.conn.execute("INSERT INTO guests(id,label,digest,created_at) VALUES(?,?,?,?)", (gid, label, fingerprint, now_iso()))
    return gid, raw


def verified_admin(request):
    return bool(request.user.is_authenticated and request.user.is_staff and request.user.is_active
                and request.session.get("admin_factor") in ("email", "recovery")
                and request.session.get("admin_until", 0) > time.time())


@ensure_csrf_cookie
@endpoint(["GET"])
def session_info(request):
    info = {"admin": verified_admin(request), "setup_required": not get_user_model().objects.filter(is_staff=True).exists()}
    challenge = email_codes.pending(request)
    if challenge and not info["admin"]:
        info["email_pending"] = challenge["stage"]
    return JsonResponse(info)


@endpoint(["POST"])
def admin_logout(request):
    logout(request)
    return JsonResponse({"ok": True})


def setup_ticket(db):
    if get_user_model().objects.filter(is_staff=True).exists():
        return None
    ticket = secrets.token_urlsafe(32)
    with db.atomic():
        db.conn.execute("""INSERT INTO local_setup VALUES(1,?,?) ON CONFLICT(id)
                           DO UPDATE SET digest=excluded.digest, expires=excluded.expires""",
                        (digest("setup", ticket), int(time.time()) + 86400))
    return ticket


def setup_allowed(db, value):
    row = db.conn.execute("SELECT digest FROM local_setup WHERE id=1 AND expires>?", (int(time.time()),)).fetchone()
    return bool(row and hmac.compare_digest(row["digest"], value) and not get_user_model().objects.filter(is_staff=True).exists())


@endpoint(["POST"])
def begin_setup(request):
    data = payload(request)
    db = private_store()
    with db.atomic():
        bucket = throttled(db, request, "initialisation")
        if not bucket:
            return limited()
        fingerprint = digest("setup", str(data.get("ticket", "")))
        trusted_origin = settings.WEB_ADMIN or request.META.get("REMOTE_ADDR") in ("127.0.0.1", "::1")
        if not trusted_origin or not setup_allowed(db, fingerprint):
            return error("La clé de première configuration est invalide ou expirée.", 403)
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 512:
            raise ValueError("Mot de passe invalide.")
        try:
            validate_password(password)
        except ValidationError as ex:
            return error(" ".join(ex.messages))
        db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
    return email_codes.issue(request, {"stage": "setup", "ticket": fingerprint,
        "password": make_password(password), "until": int(time.time()) + 1800})


def start_admin(request, user, factor):
    request.session.pop(email_codes.SESSION_KEY, None)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["admin_factor"] = factor
    request.session["admin_until"] = int(time.time()) + 12 * 3600


@endpoint(["POST"])
def finish_setup(request):
    data = payload(request)
    pending = email_codes.pending(request)
    db = private_store()
    with db.atomic():
        if hasattr(db, "lock_key"):
            db.lock_key("initialisation-administration")
        bucket = throttled(db, request, "confirmer-initialisation")
        if not bucket:
            return limited()
        if pending.get("stage") != "setup" or not setup_allowed(db, pending["ticket"]):
            return error("Recommencez la configuration avec votre clé personnelle.", 403)
        if not email_codes.consume(db, pending, data.get("code")):
            return error("Le code est incorrect, expiré ou déjà utilisé.", 401)
        with transaction.atomic():
            user = get_user_model().objects.create(username="administration", password=pending["password"], is_staff=True)
            codes = [secrets.token_hex(8).upper() for _ in range(8)]
            db.conn.executemany("INSERT INTO recovery_codes VALUES(?,?)", [(digest("recovery", c),user.pk) for c in codes])
            db.conn.execute("DELETE FROM local_setup")
            db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
        start_admin(request, user, "email")
        return JsonResponse({"recovery_codes": codes})


@endpoint(["POST"])
def admin_login(request):
    data = payload(request)
    db = private_store()
    with db.atomic():
        bucket = throttled(db, request, "administration")
        if not bucket:
            return limited()
        password = data.get("password")
        if not isinstance(password, str) or len(password) > 512:
            return error("Mot de passe incorrect.", 401)
        user = authenticate(request, username="administration", password=password)
        if not user or not user.is_staff:
            return error("Mot de passe incorrect.", 401)
        if "recovery" in data:
            token = str(data["recovery"]).strip().upper()
            if len(token) != 16 or not db.conn.execute("DELETE FROM recovery_codes WHERE user_id=? AND digest=?",
                    (user.pk, digest("recovery", token))).rowcount:
                return error("Le code de secours est incorrect ou déjà utilisé.", 401)
            email_codes.lock(db)
            db.conn.execute("DELETE FROM admin_email_challenge WHERE id=1")
            db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
            start_admin(request, user, "recovery")
            return JsonResponse({"ok": True})
    return email_codes.issue(request, {"stage": "login", "user": user.pk, "auth": user.get_session_auth_hash(), "password_bucket": bucket,
                                       "until": int(time.time()) + 1800})


def pending_user(entry):
    user = get_user_model().objects.filter(pk=entry["user"], is_active=True, is_staff=True).first()
    if user and hmac.compare_digest(user.get_session_auth_hash(), entry["auth"]):
        return user
    return None


@endpoint(["POST"])
def confirm_login(request):
    entry = email_codes.pending(request)
    if entry.get("stage") != "login":
        return error("Saisissez à nouveau votre mot de passe.", 401)
    db = private_store()
    with db.atomic():
        bucket = throttled(db, request, "confirmer-administration")
        if not bucket:
            return limited()
        user = pending_user(entry)
        if not user or not email_codes.consume(db, entry, payload(request).get("code")):
            return error("Le code est incorrect, expiré ou déjà utilisé.", 401)
        db.conn.execute("DELETE FROM login_limits WHERE bucket IN (?,?)", (bucket, entry["password_bucket"]))
        start_admin(request, user, "email")
    return JsonResponse({"ok": True})


@endpoint(["POST"])
def resend_email(request):
    entry = email_codes.pending(request)
    if entry.get("until", 0) < time.time() + email_codes.LIFETIME:
        return error("Reprenez la première étape pour recevoir un nouveau code.", 401)
    db = private_store()
    with db.atomic():
        if not throttled(db, request, "renvoi-code-administration"):
            return limited()
        valid = setup_allowed(db, entry["ticket"]) if entry["stage"] == "setup" else pending_user(entry)
        if not valid:
            return error("Reprenez la première étape pour recevoir un nouveau code.", 401)
    return email_codes.issue(request, entry)


@endpoint(["GET", "POST"])
def invitations(request, gid=None, action=None):
    if not verified_admin(request):
        return error("Connectez-vous à l’administration.", 403)
    db = registry()
    with db.atomic():
        if request.method == "GET" and not action:
            rows = db.conn.execute("SELECT id,label,created_at,last_seen,revoked,code_used FROM guests ORDER BY created_at DESC, id")
            return JsonResponse({"guests": [dict(r) for r in rows]})
        if request.method != "POST":
            return error("Méthode non autorisée.", 405)
        if not gid:
            gid, code = issue_guest(db, payload(request).get("label"))
        else:
            row = db.conn.execute("SELECT label FROM guests WHERE id=?", (gid,)).fetchone()
            if not row:
                raise FileNotFoundError
            if action == "revoke":
                db.conn.execute("UPDATE guests SET revoked=1,digest=NULL,version=version+1 WHERE id=?", (gid,))
                return JsonResponse({"ok": True})
            gid, code = issue_guest(db, row["label"], gid)
        return JsonResponse({"id": gid, "code": code, "login_url": settings.GUEST_LOGIN_URL}, status=201)


@endpoint(["GET", "POST"])
def access_requests(request, rid=None, action=None):
    if not verified_admin(request):
        return error("Connectez-vous à l’administration.", 403)
    db = registry()
    with db.atomic():
        if not rid and request.method == "GET":
            rows = db.conn.execute("""SELECT id,camping,email,created_at,status,decided_at FROM access_requests
                                      ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC, id""")
            return JsonResponse({"requests": [dict(row) for row in rows]})
        if not rid or request.method != "POST":
            return error("Méthode non autorisée.", 405)
        if hasattr(db, "lock_key"):
            db.lock_key("demande-acces/" + rid)
        row = db.conn.execute("SELECT camping,email,status FROM access_requests WHERE id=?", (rid,)).fetchone()
        if not row:
            raise FileNotFoundError
        if row["status"] != "pending":
            return error("Cette demande a déjà été traitée.", 409)
        if action == "approve":
            gid, code = issue_guest(db, row["camping"])
            db.conn.execute("UPDATE access_requests SET status='approved',decided_at=?,guest_id=? WHERE id=?",
                            (now_iso(), gid, rid))
            return JsonResponse({"id": gid, "email": row["email"], "code": code, "login_url": settings.GUEST_LOGIN_URL}, status=201)
        db.conn.execute("UPDATE access_requests SET status='declined' WHERE id=? AND status='pending'", (rid,))
        if db.conn.execute("SELECT 1 FROM access_requests WHERE id=?", (rid,)).fetchone():
            raise ValueError("L’effacement n’a pas abouti. La demande est conservée.")
        return JsonResponse({"ok": True})


@endpoint(["GET"])
def starter_stats(request):
    if not verified_admin(request):
        return error("Connectez-vous à l’administration.", 403)
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=29)
    db = registry()
    with db.atomic():
        table = "hpa_rating.starter_daily" if settings.CLOUD_ROLE else "starter_daily"
        rows = db.conn.execute(f"""SELECT event,SUM(total) AS n FROM {table}
            WHERE day BETWEEN ? AND ? GROUP BY event""", (since.isoformat(), today.isoformat()))
        totals = {row["event"]: int(row["n"]) for row in rows}
    return JsonResponse({event: totals.get(event, 0) for event in ("home","start","request","continued")})
