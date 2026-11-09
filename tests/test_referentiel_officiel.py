import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import DB, SCHEMA
from app.referentiel import CURRENT_VERSION, LEGACY_VERSION, for_audit, load
from app.scoring import applicable_criteria, compute_scores


class TestGrilleOfficielle(unittest.TestCase):
    def setUp(self):
        self.ref = load()
        self.profile = {"type": "camping", "mention": "tourisme"}

    def rows(self, stars, profile=None, items=None):
        return {r["id"]: r for r in applicable_criteria(self.ref, profile or self.profile, stars, items)}

    def test_numerotation_points_et_contraintes(self):
        criteria = self.ref["criteria"]
        self.assertEqual([c["id"] for c in criteria], list(map(str, range(1, 196))))
        self.assertTrue(all(set(c["rules"]) == set("12345") for c in criteria))
        self.assertEqual(sorted({c["source_page"] for c in criteria}), list(range(1, 15)))
        self.assertEqual([c["id"] for c in criteria if c.get("points_min")], ["22", "24", "115", "131"])
        rows = self.rows(3)
        self.assertEqual(rows["9"]["code"], "X")
        self.assertEqual({i for i in rows if rows[i]["code"] == "ONC"}, set("7 19 20 40 53 54 57".split()))
        self.assertEqual(rows["20"]["points"], 0)
        self.assertTrue(rows["2"]["ajo"])
        self.assertEqual(criteria[174]["rules"]["4"]["exigence"], "1 par tranche de 160 emplacements")

    def test_applicabilite_profils(self):
        small = self.rows(4, {**self.profile, "nb_emplacements": 199, "wifi_sans_positionnement": True,
                              "has_locatifs": False, "adults_only": True, "mention": "loisirs"})
        for cid in ("11", "14", "114"):
            self.assertEqual(small[cid]["code"], "O", cid)
        for cid in ("39", "48", "49", "53", "143"):
            self.assertEqual(small[cid]["code"], "NA", cid)
        self.assertEqual(self.rows(4, {**self.profile, "nb_emplacements": 200})["14"]["code"], "X")
        prl = self.rows(2, {"type": "prl", "has_reception": False, "nb_emplacements_caravanes": 0})
        self.assertEqual(prl["3"]["code"], "PRQ")
        for cid in ("1", "20", "26", "38", "40", "59", "95"):
            self.assertEqual(prl[cid]["code"], "NA", cid)

    def test_seuils_bonifications_et_validation_par_equivalence(self):
        items = {"21": {"status": "VALIDATED", "validated_stars": 3},
                 "22": {"status": "VALIDATED", "awarded_points": 2, "validated_stars": 3},
                 "44": {"status": "VALIDATED"}, "61": {"status": "VALIDATED"}}
        self.assertEqual(self.rows(1, items=items)["59"]["via"], "60")
        self.assertEqual(self.rows(3, items=items)["43"]["via"], "44")
        at_three = compute_scores(self.ref, self.profile, 3, items)
        without_bonus = compute_scores(self.ref, self.profile, 3, {k:v for k,v in items.items() if k != "22"})
        self.assertEqual(at_three["o"]["obtained"] - without_bonus["o"]["obtained"], 2)
        for cid in ("21", "22"):
            self.assertEqual(self.rows(4, items=items)[cid]["status"], "TODO")

    def test_ancien_dossier_ne_change_pas_de_critere(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.db"
            with sqlite3.connect(path) as old:
                old.executescript(SCHEMA)
                old.executemany("INSERT INTO audits(id,name,created_at,updated_at) VALUES(?,?,?,?)",
                                [("old","A","2025","2025"), ("empty","B","2025","2025")])
                old.execute("INSERT INTO items(audit_id,criterion_id,status,updated_at) VALUES('old','7','VALIDATED','2025')")
            old.close()
            for _ in range(2):
                db = DB(path)
                try:
                    legacy = db.get_audit("old")
                    self.assertEqual(legacy["reference_version"], LEGACY_VERSION)
                    self.assertEqual(db.get_audit("empty")["reference_version"], CURRENT_VERSION)
                    seven = next(c for c in for_audit(legacy)["criteria"] if c["id"] == "7")
                    self.assertIn("parking", seven["title"])
                    self.assertEqual(db.clone_audit("old", "Copie")["reference_version"], LEGACY_VERSION)
                finally:
                    db.close()
