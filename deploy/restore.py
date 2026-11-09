"""Restore a trusted backup on a new, stopped Hpa Rating VM. Ubuntu 24.04 / Python 3.12+."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

VOLUMES = ("guest_state", "admin_state", "invitations", "tls", "caddy_config")


def validate_member(member):
    name = PurePosixPath(member.name)
    if (name.is_absolute() or ".." in name.parts or "\\" in member.name
            or not (member.isdir() or member.isreg()) or (not name.parts and not member.isdir())):
        raise ValueError("Entrée interdite dans la sauvegarde.")


def restore(source, targets):
    if set(targets) != set(VOLUMES) or len({v.resolve() for v in targets.values()}) != len(VOLUMES):
        raise ValueError("Les cinq volumes distincts sont requis.")
    expected = {}
    for line in (source / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](?:\./)?([a-z_]+)\.tar\.gz", line)
        if not match or match[2] in expected:
            raise ValueError("Manifeste de sauvegarde invalide.")
        expected[match[2]] = match[1]
    if set(expected) != set(VOLUMES):
        raise ValueError("La sauvegarde doit contenir les cinq volumes.")

    # Complete every preflight before writing the first byte to any volume.
    for name in VOLUMES:
        dest = targets[name]
        if not dest.is_dir() or dest.is_symlink() or any(p.is_symlink() or not p.is_dir() for p in dest.rglob("*")):
            raise ValueError(f"Le volume {name} n’est pas vide ; restauration annulée.")
        archive = source / (name + ".tar.gz")
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected[name]:
                raise ValueError(f"Empreinte invalide pour {name}.")
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                validate_member(member)
    for name in VOLUMES:
        with tarfile.open(source / (name + ".tar.gz"), "r:gz") as tar:
            def safe(info, path):
                validate_member(info)
                # Preserve numeric owners (notably UID 10001), never special permission bits.
                return tarfile.tar_filter(info.replace(mode=info.mode & 0o777), path)
            tar.extractall(targets[name], numeric_owner=True, filter=safe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sauvegarde", type=Path)
    source = parser.parse_args().sauvegarde.resolve(strict=True)
    if getattr(os, "geteuid", lambda: -1)() != 0:
        parser.exit(1, "Exécuter avec sudo sur la nouvelle VM Linux.\n")
    targets = {}
    for name in VOLUMES:
        volume = "hpa-rating_" + name
        active = subprocess.check_output(["docker", "ps", "-q", "--filter", "volume=" + volume], text=True).strip()
        if active:
            parser.exit(1, f"Un conteneur utilise {volume} ; aucun fichier n’a été écrit.\n")
        path = subprocess.check_output(["docker", "volume", "inspect", "-f", "{{.Mountpoint}}", volume], text=True)
        targets[name] = Path(path.strip())
    restore(source, targets)
    print("Les cinq volumes ont été restaurés. Les services sont toujours arrêtés.")


if __name__ == "__main__":
    main()
