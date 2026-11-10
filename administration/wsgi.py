import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "administration.settings")
if os.environ.get("VERCEL") and os.environ.get("HPA_SUPABASE_ROLE") != "webadmin":
    raise RuntimeError("L’administration en ligne exige son rôle PostgreSQL dédié.")
application = get_wsgi_application()
