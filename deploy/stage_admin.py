"""Build the standalone Vercel source tree in a new, empty directory."""
import argparse
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parents[1]


def stage(target):
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Le répertoire de publication doit être vide.")
    for pattern in ("administration/*.py", "administration/static/*.html", "administration/static/*.css",
                    "administration/static/*.js", "hpa_shared/*.py", "hpa_shared/static/brand.css",
                    "hpa_shared/static/common.js", "hpa_shared/static/logo.png", "hpa_shared/supabase-root-2021.crt"):
        for source in ROOT.glob(pattern):
            dest = target / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, dest)
    copyfile(ROOT / "vercel.json", target / "vercel.json")
    deps = (ROOT / "requirements.txt").read_text().splitlines()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "hpa-rating-administration"\nversion = "0.1.0"\nrequires-python = ">=3.12,<3.13"\n'
        + "dependencies = [\n" + "".join('    "' + dep + '",\n' for dep in deps if dep.strip()) + "]\n\n"
        + '[tool.vercel]\nentrypoint = "administration.wsgi:application"\n', encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    stage(parser.parse_args().target.resolve())
