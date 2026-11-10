import hashlib
import hmac
from hpa_shared.settings import *

SECRET_KEY = hmac.new(APPLICATION_KEY.encode(), b"hpa/operator-session/v1", hashlib.sha256).hexdigest()
ROOT_URLCONF = "administration.urls"
# Keep the existing password, authenticator and Django user IDs.
DATABASES = sqlite_database("access.sqlite3")
if CLOUD_ROLE:
    if CLOUD_ROLE != "admin":
        raise ValueError("La console exige son propre rôle.")
    from hpa_shared.postgres import database
    DATABASES["hpa_registry"] = database("admin")
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
