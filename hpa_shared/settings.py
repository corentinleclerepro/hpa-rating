import os
import secrets
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HPA_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


def local_key():
    target = DATA_DIR / "application.key"
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


INVITATION_KEY = local_key()
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
