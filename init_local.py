"""Optional local migration / first demo — never imported by either web service."""
import argparse
from pathlib import Path
from hpa_shared.runtime import prepare


def main():
    parser = argparse.ArgumentParser(description="Préparer une fiche privée et rattacher les anciens dossiers")
    parser.add_argument("fiche")
    args = parser.parse_args()
    prepare("administration.settings")
    from django.conf import settings
    from administration.state import private_store
    from administration.views import issue_guest, setup_ticket
    from hpa_shared.registry import registry
    from app.storage import attach_previous, store
    dossiers = store()
    with Path(args.fiche).open("x", encoding="utf-8-sig") as handle, registry().atomic(), private_store().atomic(), dossiers.atomic():
        ticket = setup_ticket(private_store())
        lines = ["Hpa Rating · Camp Compagnon — Fiche privée", ""]
        if ticket:
            lines += ["Console privée : http://127.0.0.1:8001/", "Clé de première configuration (24 h) :", ticket, ""]
        gid, code = issue_guest(registry(), "Essai privé · Clairière Bleue")
        attach_previous(dossiers, gid)
        lines += ["Mon espace : " + settings.GUEST_LOGIN_URL, "Code invité personnel :", code, ""]
        handle.write("\n".join(lines))
    print("La fiche d’accès locale est prête.", flush=True)


if __name__ == "__main__":
    main()
