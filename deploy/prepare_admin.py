"""Provision the isolated operator schema and a one-use private setup document."""
import argparse
import os
import sys
from pathlib import Path


def prepare_admin(ticket_file):
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection
    from django.contrib.auth import get_user_model
    from administration.state import private_store
    from administration.views import setup_ticket

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, current_schema()")
        if cursor.fetchone() != ("hpa_rating_webadmin", "hpa_rating_staff") or not settings.WEB_ADMIN:
            raise RuntimeError("Le provisionnement exige le rôle et le schéma de l’administration.")
    call_command("migrate", interactive=False, verbosity=0)
    if get_user_model().objects.filter(is_staff=True).exists():
        return False
    with open(ticket_file, "x", encoding="utf-8", opener=lambda path,flags: os.open(path,flags,0o600)) as output:
        db = private_store()
        with db.atomic():
            db.lock_key("initialisation-administration")
            ticket = setup_ticket(db)
            if not ticket:
                raise RuntimeError("Le compte administrateur est déjà activé.")
            output.write("Activer votre espace administration Hpa Rating\n\nhttps://" + settings.ALLOWED_HOSTS[0] +
                         "/\n\nClé personnelle de première configuration, valable 24 heures et utilisable une fois\n" + ticket +
                         "\n\nChoisissez votre mot de passe sur le site, associez votre application d’authentification "
                         "et conservez vos codes de secours en lieu sûr.\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket", type=Path)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "administration.settings")
    import django
    django.setup()
    created = prepare_admin(parser.parse_args().ticket)
    print("Fiche d’activation prête." if created else "Le compte administrateur est déjà activé.")
