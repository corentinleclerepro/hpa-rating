from hpa_shared.settings import *

SECRET_KEY = INVITATION_KEY
ROOT_URLCONF = "app.urls"
DATABASES = sqlite_database("guest-sessions.sqlite3")
INSTALLED_APPS = ["django.contrib.sessions"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.common.CommonMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware", "app.http.EvidenceBody",
              "django.middleware.csrf.CsrfViewMiddleware", "hpa_shared.http.PrivateHeaders"]
APPEND_SLASH = False
SESSION_COOKIE_NAME = "hpa_session"
CSRF_COOKIE_NAME = "hpa_csrf"
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024 * 1024
