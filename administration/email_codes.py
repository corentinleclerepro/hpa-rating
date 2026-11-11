"""Deliver and consume the single operator's browser-bound email challenge."""
import hmac
import secrets
import smtplib
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import JsonResponse

from hpa_shared.http import error
from hpa_shared.registry import digest
from .state import private_store

LIFETIME = 600
RESEND_DELAY = 60
MAX_FAILURES = 5
SESSION_KEY = "admin_email_pending"


def pending(request):
    entry = request.session.get(SESSION_KEY) or {}
    return entry if entry.get("until", 0) > time.time() else {}


def lock(db):
    # SQLite already holds BEGIN IMMEDIATE. PostgreSQL also serializes the first insert.
    if hasattr(db, "lock_key"):
        db.lock_key("administration-code-email")


def signature(stage, nonce, code):
    return digest("admin-email", f"{settings.ADMIN_EMAIL}|{stage}|{nonce}|{code}")


def issue(request, details):
    try:
        validate_email(settings.ADMIN_EMAIL)
    except ValidationError:
        return error("L’envoi des codes par e-mail n’est pas encore configuré.", 503)
    if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not settings.EMAIL_HOST_PASSWORD:
        return error("L’envoi des codes par e-mail n’est pas encore configuré.", 503)
    now = int(time.time())
    nonce = secrets.token_hex(24)
    code = f"{secrets.randbelow(1_000_000):06d}"
    db = private_store()
    with db.atomic():
        lock(db)
        last = db.conn.execute("SELECT sent_at FROM admin_email_challenge WHERE id=1").fetchone()
        if last and last["sent_at"] + RESEND_DELAY > now:
            wait = last["sent_at"] + RESEND_DELAY - now
            reply = error(f"Un code a déjà été envoyé. Vous pourrez en demander un autre dans {wait} s.", 429)
            reply["Retry-After"] = str(wait)
            return reply
        db.conn.execute("""INSERT INTO admin_email_challenge(id,nonce,proof,sent_at,expires,failures)
            VALUES(1,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET nonce=excluded.nonce,proof=excluded.proof,
            sent_at=excluded.sent_at,expires=excluded.expires,failures=0""",
            (nonce, signature(details["stage"], nonce, code), now, now + LIFETIME))
    action = "activer votre administration" if details["stage"] == "setup" else "vous connecter à votre administration"
    try:
        sent = send_mail("Votre code pour l’administration Hpa Rating",
            f"Votre code pour {action} Hpa Rating est\n\n{code}\n\n"
            "Saisissez ces six chiffres dans le navigateur où vous avez fait la demande. "
            "Ce code est valable 10 minutes et utilisable une seule fois. "
            "Si vous n’avez pas fait cette demande, vous pouvez ignorer cet e-mail.",
            settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])
    except (OSError, smtplib.SMTPException):
        sent = 0
    if not sent:
        with db.atomic():
            db.conn.execute("DELETE FROM admin_email_challenge WHERE nonce=?", (nonce,))
        return error("L’e-mail n’a pas pu être envoyé. Réessayez dans un instant.", 503)
    request.session.cycle_key()
    request.session[SESSION_KEY] = {**details, "nonce": nonce}
    return JsonResponse({"email_pending": details["stage"], "expires_in": LIFETIME})


def consume(db, entry, code):
    """The caller keeps the transaction open until the setup or login is complete."""
    lock(db)
    row = db.conn.execute("SELECT * FROM admin_email_challenge WHERE id=1 AND nonce=?",
                          (entry["nonce"],)).fetchone()
    if not row or row["expires"] <= time.time() or row["failures"] >= MAX_FAILURES:
        return False
    if (not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdecimal()
            or not hmac.compare_digest(row["proof"], signature(entry["stage"], row["nonce"], code))):
        db.conn.execute("UPDATE admin_email_challenge SET failures=failures+1 WHERE id=1")
        return False
    db.conn.execute("DELETE FROM admin_email_challenge WHERE id=1")
    return True
