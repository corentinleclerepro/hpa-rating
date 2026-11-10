import argparse
import shutil
from hpa_shared.runtime import prepare, serve


def configure():
    prepare("app.settings")
    from .storage import store
    from .legacy_sessions import import_guest_sessions
    from hpa_shared.registry import registry
    from django.conf import settings
    registry()
    if settings.CLOUD_ROLE:
        return store()
    import_guest_sessions()
    db = store()
    # Finish or restore a deletion interrupted between the filesystem move and SQLite commit.
    removed = settings.DATA_DIR / ".removed"
    if removed.is_dir():
        for pending in removed.iterdir():
            parts = pending.name.split("-")
            if len(parts) != 3 or parts[0] not in ("dossiers", "exports") or not all(c in "0123456789abcdef" for c in parts[1]):
                continue
            target = settings.DATA_DIR / parts[0] / parts[1]
            if db.get_audit(parts[1]) and not target.exists():
                pending.rename(target)
            elif not db.get_audit(parts[1]):
                shutil.rmtree(pending)
    return db


def main():
    parser = argparse.ArgumentParser(description="Hpa Rating · Camp Compagnon — espace invité")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    args = parser.parse_args()
    configure()
    serve(args.host, args.port, "Hpa Rating")
