"""A damaged backup must never partially overwrite another volume."""
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

from deploy.restore import VOLUMES, restore


@unittest.skipIf(sys.version_info < (3, 12), "La restauration vise Ubuntu 24.04 / Python 3.12+")
class RestoringVolumes(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.source = root / "backup"
        self.source.mkdir()
        self.targets = {v: root / v for v in VOLUMES}
        for dest in self.targets.values():
            dest.mkdir()
        self.archives()

    def archives(self, *, misplaced=None):
        lines = []
        for name in VOLUMES:
            pack = self.source / (name + ".tar.gz")
            with tarfile.open(pack, "w:gz") as tar:
                entry = tarfile.TarInfo("../ailleurs" if misplaced == name else "./exemple")
                data = name.encode()
                entry.size = len(data)
                tar.addfile(entry, BytesIO(data))
            lines.append(f"{hashlib.sha256(pack.read_bytes()).hexdigest()}  ./{pack.name}\n")
        (self.source / "SHA256SUMS").write_text("".join(lines), encoding="ascii")

    def test_restores_each_store_and_preserves_existing_data(self):
        restore(self.source, self.targets)
        for name, dest in self.targets.items():
            self.assertEqual((dest / "exemple").read_text(), name)
        existing = self.targets["guest_state"] / "exemple"
        existing.write_text("dossier déjà en service")
        with self.assertRaisesRegex(ValueError, "pas vide"):
            restore(self.source, self.targets)
        self.assertEqual(existing.read_text(), "dossier déjà en service")

    def test_damage_or_traversal_in_last_archive_prevents_any_writes(self):
        (self.source / (VOLUMES[-1] + ".tar.gz")).write_bytes(b"incomplet")
        with self.assertRaisesRegex(ValueError, "Empreinte invalide"):
            restore(self.source, self.targets)
        self.archives(misplaced=VOLUMES[-1])
        with self.assertRaisesRegex(ValueError, "interdite"):
            restore(self.source, self.targets)
        self.assertFalse(any(list(directory.iterdir()) for directory in self.targets.values()))
