"""Start only the invitation console, bound to the loopback interface."""
import argparse
from pathlib import Path
from hpa_shared.runtime import prepare, serve


def main():
    parser = argparse.ArgumentParser(description="Hpa Rating · Camp Compagnon — console privée d’invitations")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--setup-key", metavar="FICHIER", help="Préparer la première connexion sur ce poste")
    args = parser.parse_args()
    prepare("administration.settings")
    from administration.state import private_store
    from hpa_shared.registry import registry
    private_store()
    registry()
    if args.setup_key:
        from administration.views import setup_ticket
        from django.contrib.auth import get_user_model
        if get_user_model().objects.filter(is_staff=True).exists():
            parser.exit(message="L’administration est déjà configurée. Utilisez votre mot de passe et votre application.\n")
        with Path(args.setup_key).open("x", encoding="utf-8-sig") as output, private_store().atomic():
            ticket = setup_ticket(private_store())
            if not ticket:
                raise RuntimeError("L’administration est déjà configurée.")
            output.write(f"Console privée : http://127.0.0.1:{args.port}/\nClé de première configuration (24 h) :\n{ticket}\n")
        print("La fiche privée est prête.", flush=True)
        return
    serve("127.0.0.1", args.port, "Administration Hpa Rating")


if __name__ == "__main__":
    main()
