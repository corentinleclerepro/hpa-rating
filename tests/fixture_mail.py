"""Mail captured in the private temporary directory of a test server."""
from email import policy
from email.parser import BytesParser
import os
from pathlib import Path
import re
import runpy
import sys

RECIPIENT = "operator@example.invalid"


def latest_code(data_dir):
    files = (Path(data_dir) / "test-mail").glob("*.log")
    latest = max(files, key=lambda p: p.stat().st_mtime_ns)
    message = BytesParser(policy=policy.default).parsebytes(latest.read_bytes())
    assert str(message["To"]) == RECIPIENT
    return re.search(r"^([0-9]{6})\s*$", message.get_body().get_content(), re.MULTILINE)[1]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["DJANGO_SETTINGS_MODULE"] = "administration.settings"
    from django.conf import settings
    settings.ADMIN_EMAIL = RECIPIENT
    settings.EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    settings.EMAIL_FILE_PATH = Path(os.environ["HPA_DATA_DIR"]) / "test-mail"
    sys.argv = sys.argv[1:]
    runpy.run_path(str(root / sys.argv[0]), run_name="__main__")
