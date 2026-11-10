import os
import re
import secrets
import time
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent
CLOUD_ROLE = os.environ.get("HPA_SUPABASE_ROLE", "")
if CLOUD_ROLE not in ("", "guest", "admin", "webadmin"):
    raise ValueError("Rôle Hpa Rating inconnu.")
WEB_ADMIN = CLOUD_ROLE == "webadmin"
PRODUCTION = os.environ.get("HPA_ENV") == "production" or CLOUD_ROLE in ("guest", "webadmin")
default_data = Path(tempfile.gettempdir()) / "hpa-rating-runtime" if CLOUD_ROLE in ("guest", "webadmin") else BASE_DIR / "data"
DATA_DIR = Path(os.environ.get("HPA_DATA_DIR", default_data)).resolve()
REGISTRY_DIR = Path(os.environ.get("HPA_REGISTRY_DIR", DATA_DIR)).resolve()
if PRODUCTION and not CLOUD_ROLE and (not os.environ.get("HPA_DATA_DIR") or not os.environ.get("HPA_REGISTRY_DIR")
                   or DATA_DIR == REGISTRY_DIR or DATA_DIR in REGISTRY_DIR.parents or REGISTRY_DIR in DATA_DIR.parents):
    raise ValueError("La production exige deux répertoires persistants distincts : HPA_DATA_DIR et HPA_REGISTRY_DIR.")


def guest_origin():
    default = "" if PRODUCTION else "http://localhost:8000"
    value = os.environ.get("HPA_GUEST_ORIGIN", default).rstrip("/")
    url = urlsplit(value)
    host = url.hostname or ""
    authority = ("[" + host + "]" if ":" in host else host) + (f":{url.port}" if url.port else "")
    if (url.scheme not in ("http", "https") or not host or url.path or "?" in value or "#" in value
            or url.username is not None or url.password is not None or any(ord(c) <= 32 for c in value)
            or url.netloc.lower() != authority or url.port == 0):
        raise ValueError("HPA_GUEST_ORIGIN doit contenir uniquement l’origine de connexion.")
    if PRODUCTION:
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if (url.scheme != "https" or len(host) > 253 or not re.fullmatch(rf"(?:{label}\.)+[a-z]{{2,63}}", host)
                or host.endswith((".localhost", ".local"))):
            raise ValueError("La production exige l’origine HTTPS exacte de l’espace invité.")
    return value


GUEST_ORIGIN = guest_origin()
DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
REGISTRY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def local_key(target, protected_state=()):
    if PRODUCTION and any((target.parent / name).exists() for name in protected_state) and not target.exists():
        raise RuntimeError(f"Clé manquante ({target.name}) : restaurez-la depuis la sauvegarde de ce volume.")
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # The other process may still be finishing the first write.
        for attempt in range(20):
            key = target.read_text(encoding="ascii").strip()
            if len(key) >= 40:
                return key
            time.sleep(0.025)
        raise RuntimeError("La clé locale de l’application est incomplète.")
    key = secrets.token_urlsafe(64)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(key)
    return key


def required_key(name):
    value = os.environ.get(name, "")
    if len(value) < 40:
        raise ValueError(f"Configuration privée manquante : {name}")
    return value


APPLICATION_KEY = (required_key("HPA_CLOUD_APP_KEY") if CLOUD_ROLE in ("guest", "webadmin") else
                   local_key(DATA_DIR / "application.key", ("app.db", "access.sqlite3", "guest-sessions.sqlite3", "console-state.sqlite3")))
INVITATION_KEY = (required_key("HPA_INVITATION_KEY") if CLOUD_ROLE else APPLICATION_KEY if REGISTRY_DIR == DATA_DIR
                  else local_key(REGISTRY_DIR / "invitation.key", ("invitations.sqlite3",)))
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 7 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.environ.get("HPA_HTTPS") == "1"
SECURE_REFERRER_POLICY = "no-referrer"
CSRF_FAILURE_VIEW = "hpa_shared.http.csrf_failure"
LANGUAGE_CODE = "fr"
USE_TZ = True
TIME_ZONE = "Europe/Paris"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"


def sqlite_database(filename):
    return {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / filename,
                        "OPTIONS": {"timeout": 20}}}
