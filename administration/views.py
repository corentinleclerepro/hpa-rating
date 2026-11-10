import base64
import hmac
import io
import secrets
import time
import uuid

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django_otp import login as verify_session
from django_otp.plugins.otp_totp.models import TOTPDevice
from hpa_shared.registry import now_iso, registry, digest, canonical, throttled, limited
from hpa_shared.http import endpoint, error, payload
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
    return bool(request.user.is_authenticated and request.user.is_staff and request.user.is_verified()
                and request.session.get("admin_until", 0) > time.time())


@ensure_csrf_cookie
@endpoint(["GET"])
def session_info(request):
    return JsonResponse({"admin": verified_admin(request), "setup_required": not get_user_model().objects.filter(is_staff=True).exists()})


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
        key = secrets.token_hex(20)
        user = get_user_model()(username="administration")
        device = TOTPDevice(user=user, name=settings.OTP_TOTP_ISSUER, key=key)
        buffer = io.BytesIO()
        qrcode.make(device.config_url, image_factory=qrcode.image.svg.SvgPathImage).save(buffer)
        request.session.cycle_key()
        request.session["setup"] = {"ticket": fingerprint, "password": make_password(password), "key": key, "until": time.time()+900}
        return JsonResponse({"qr": "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode(),
                             "manual_key": base64.b32encode(bytes.fromhex(key)).decode()})


def start_admin(request, user, device):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    verify_session(request, device)
    request.session["admin_until"] = int(time.time()) + 12 * 3600


@endpoint(["POST"])
def finish_setup(request):
    data = payload(request)
    pending = request.session.get("setup") or {}
    db = private_store()
    with db.atomic():
        if hasattr(db, "lock_key"):
            db.lock_key("initialisation-administration")
        bucket = throttled(db, request, "confirmer-initialisation")
        if not bucket:
            return limited()
        if pending.get("until", 0) < time.time() or not setup_allowed(db, pending.get("ticket", "")):
            return error("Recommencez la configuration avec votre clé personnelle.", 403)
        with transaction.atomic():
            user = get_user_model().objects.create(username="administration", password=pending["password"], is_staff=True)
            device = TOTPDevice.objects.create(user=user, name="Application", key=pending["key"], confirmed=True)
            if not device.verify_token(str(data.get("otp", ""))):
                transaction.set_rollback(True)
                return error("Le code à six chiffres est incorrect.", 401)
            codes = [secrets.token_hex(8).upper() for _ in range(8)]
            db.conn.executemany("INSERT INTO recovery_codes VALUES(?,?)", [(digest("recovery", c),user.pk) for c in codes])
            db.conn.execute("DELETE FROM local_setup")
            db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
        request.session.pop("setup", None)
        start_admin(request, user, device)
        return JsonResponse({"recovery_codes": codes})


@endpoint(["POST"])
def admin_login(request):
    data = payload(request)
    db = private_store()
    with db.atomic():
        bucket = throttled(db, request, "administration")
        if not bucket:
            return limited()
        user = authenticate(request, username="administration", password=str(data.get("password", ""))[:512])
        if user and user.is_staff:
            token = str(data.get("otp", "")).strip()
            devices = TOTPDevice.objects.filter(user=user, confirmed=True)
            if settings.WEB_ADMIN:
                devices = devices.select_for_update()
            device = devices.first()
            valid = False
            if device:
                if len(token) == 6 and token.isdecimal():
                    valid = device.verify_token(token)
                elif len(token) == 16:
                    valid = db.conn.execute("DELETE FROM recovery_codes WHERE user_id=? AND digest=?",
                                            (user.pk, digest("recovery", token.upper()))).rowcount == 1
            if valid:
                db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
                start_admin(request, user, device)
                return JsonResponse({"ok": True})
        return error("Mot de passe ou code d’authentification incorrect.", 401)


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
        db.conn.execute("UPDATE access_requests SET status='declined',decided_at=? WHERE id=?", (now_iso(), rid))
        return JsonResponse({"ok": True})
