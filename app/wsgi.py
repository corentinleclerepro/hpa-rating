import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
if os.environ.get("VERCEL") and os.environ.get("HPA_SUPABASE_ROLE") != "guest":
    raise RuntimeError("Le déploiement public exige son accès Supabase dédié.")
application = get_wsgi_application()
