import hashlib
import hmac
from urllib.parse import urlsplit
from hpa_shared.settings import *

SECRET_KEY = hmac.new(APPLICATION_KEY.encode(), b"hpa/operator-session/v1", hashlib.sha256).hexdigest()
ROOT_URLCONF = "administration.urls"
# Keep the existing password, authenticator and Django user IDs.
DATABASES = sqlite_database("access.sqlite3")
if CLOUD_ROLE:
    from hpa_shared.postgres import database
    if WEB_ADMIN:
        DATABASES = {"default": database("webadmin")}
        admin_host = os.environ["HPA_ADMIN_HOST"]
        if (not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", admin_host)
                or admin_host == urlsplit(GUEST_ORIGIN).hostname):
            raise ValueError("L’administration exige son propre nom d’hôte HTTPS.")
        ALLOWED_HOSTS = [admin_host]
        CSRF_TRUSTED_ORIGINS = ["https://" + admin_host]
        SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
        SECURE_SSL_REDIRECT = True
        SECURE_HSTS_SECONDS = 86400
        if os.environ.get("VERCEL") == "1":
            SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    elif CLOUD_ROLE == "admin":
        DATABASES["hpa_registry"] = database("admin")
    else:
        raise ValueError("L’administration exige son propre rôle.")
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
                  "django_otp", "django_otp.plugins.otp_totp"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.middleware.common.CommonMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
              "django.contrib.auth.middleware.AuthenticationMiddleware", "django_otp.middleware.OTPMiddleware",
              "hpa_shared.http.PrivateHeaders"]
APPEND_SLASH = False
SESSION_COOKIE_NAME = "hpa_console_session"
CSRF_COOKIE_NAME = "hpa_console_csrf"
SESSION_COOKIE_AGE = 12 * 3600
OTP_TOTP_ISSUER = "Hpa Rating"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
                            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
                            {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
GUEST_LOGIN_URL = GUEST_ORIGIN + "/connexion"
