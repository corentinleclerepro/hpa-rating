from urllib.parse import urlsplit
from hpa_shared.settings import *

SECRET_KEY = APPLICATION_KEY
ROOT_URLCONF = "app.urls"
DATABASES = sqlite_database("guest-sessions.sqlite3")
if CLOUD_ROLE:
    if CLOUD_ROLE != "guest":
        raise ValueError("Le serveur invité exige son propre rôle.")
    from hpa_shared.postgres import database
    DATABASES = {"default": database("guest")}
INSTALLED_APPS = ["django.contrib.sessions"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.common.CommonMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware", "app.http.EvidenceBody",
              "django.middleware.csrf.CsrfViewMiddleware", "hpa_shared.http.PrivateHeaders"]
APPEND_SLASH = False
SESSION_COOKIE_NAME = "hpa_session"
CSRF_COOKIE_NAME = "hpa_csrf"
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024 * 1024
if PRODUCTION:
    ALLOWED_HOSTS = [urlsplit(GUEST_ORIGIN).hostname]
    CSRF_TRUSTED_ORIGINS = [GUEST_ORIGIN]
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_SSL_HOST = urlsplit(GUEST_ORIGIN).netloc
    SECURE_HSTS_SECONDS = 86400
    if CLOUD_ROLE and os.environ.get("VERCEL") == "1":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        # After a custom domain is connected Vercel may put that domain in its system variable.
        for key in ("VERCEL_PROJECT_PRODUCTION_URL", "HPA_VERCEL_ALIAS"):
            alias = os.environ.get(key, "")
            if re.fullmatch(r"[a-z0-9-]+\.vercel\.app", alias) and alias not in ALLOWED_HOSTS:
                ALLOWED_HOSTS.append(alias)
