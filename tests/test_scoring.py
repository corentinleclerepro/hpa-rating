import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scoring import compute_scores, reachable_stars, rule_for, applicable_criteria

REF = {
    "criteria": [
        {"id": "PRQ1", "rules": {"*": {"code": "PRQ", "points": 0}}},
        {"id": "C1", "rules": {"*": {"code": "X", "points": 100}}},
        {"id": "C2", "rules": {"*": {"code": "X", "points": 100}}},
        {"id": "C3", "rules": {"*": {"code": "ONC", "points": 5}}},
        {"id": "C6", "rules": {"*": {"code": "X", "points": 10}}},
        {"id": "C4", "rules": {"1": {"code": "O", "points": 20},
                              "2": {"code": "O", "points": 30},
                              "3": {"code": "O", "points": 40},
                              "4": {"code": "O", "points": 50},
                              "5": {"code": "X", "points": 5}}},
        {"id": "P1", "applies_to": ["prl"], "rules": {"*": {"code": "X", "points": 8}}},
        {"id": "C5", "loisirs_becomes": "O", "rules": {"*": {"code": "X", "points": 4}}},
        {"id": "POOL1", "conditions": {"has_pool": True}, "rules": {"*": {"code": "O", "points": 10}}},
    ]
}

PROFILE = {"type": "camping", "mention": "tourisme", "has_pool": False}
ALL_OK = {c["id"]: {"status": "VALIDATED"} for c in REF["criteria"]}


class TestRuleFor(unittest.TestCase):
    def test_prl_only_excluded_for_camping(self):
        r = rule_for(REF["criteria"][6], 3, PROFILE)
        self.assertEqual(r["code"], "NA")

    def test_prl_only_included_for_prl(self):
        r = rule_for(REF["criteria"][6], 3, {"type": "prl", "mention": "loisirs"})
        self.assertEqual(r["code"], "X")

    def test_conditions_filter(self):
        r = rule_for(REF["criteria"][8], 3, PROFILE)
        self.assertEqual(r["code"], "NA")
        r = rule_for(REF["criteria"][8], 3, {**PROFILE, "has_pool": True})
        self.assertEqual(r["code"], "O")

    def test_loisirs_becomes_optionnel(self):
        r = rule_for(REF["criteria"][7], 3, PROFILE)
        self.assertEqual(r["code"], "X")
        r = rule_for(REF["criteria"][7], 3, {"type": "camping", "mention": "loisirs"})
        self.assertEqual(r["code"], "O")

    def test_per_star_rule(self):
        self.assertEqual(rule_for(REF["criteria"][5], 1, PROFILE)["code"], "O")
        self.assertEqual(rule_for(REF["criteria"][5], 5, PROFILE)["code"], "X")


class TestComputeScores(unittest.TestCase):
    def test_all_validated_3_stars_eligible(self):
        s = compute_scores(REF, PROFILE, 3, ALL_OK)
        self.assertTrue(s["eligible"])
        self.assertEqual(s["x"]["total"], 214)
        self.assertEqual(s["o"]["total"], 40)
        self.assertEqual(s["o"]["base_required"], 8)
        self.assertEqual(s["o"]["required"], 8)

    def test_prq_missing_blocks(self):
        st = dict(ALL_OK)
        st["PRQ1"] = {"status": "NON_COMPLIANT"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertFalse(s["eligible"])
        self.assertEqual(s["blockers"][0]["type"], "PRQ")

    def test_onc_missing_blocks_even_with_points(self):
        st = dict(ALL_OK)
        st["C3"] = {"status": "NON_COMPLIANT"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertFalse(s["eligible"])
        self.assertIn("ONC", [b["type"] for b in s["blockers"]])

    def test_lost_within_margin_needs_3x_compensation(self):
        st = dict(ALL_OK)
        st["C6"] = {"status": "NON_COMPLIANT"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertTrue(s["x"]["within_margin"])
        self.assertEqual(s["x"]["margin_points"], 10.7)
        self.assertEqual(s["o"]["compensation"], 30)
        self.assertEqual(s["o"]["required"], 38)
        self.assertTrue(s["eligible"])

    def test_lost_within_margin_without_extra_carte_points_fails(self):
        st = dict(ALL_OK)
        st["C6"] = {"status": "NON_COMPLIANT"}
        st["C4"] = {"status": "NON_COMPLIANT"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertFalse(s["eligible"])
        self.assertFalse(s["o"]["ok"])

    def test_lost_beyond_margin_fails(self):
        st = dict(ALL_OK)
        st["C1"] = {"status": "NON_COMPLIANT"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertFalse(s["x"]["within_margin"])
        self.assertFalse(s["eligible"])

    def test_pending_counts_as_not_attained(self):
        st = dict(ALL_OK)
        st["C1"] = {"status": "TODO"}
        s = compute_scores(REF, PROFILE, 3, st)
        self.assertEqual(s["x"]["pending"], 100)
        self.assertFalse(s["x"]["within_margin"])
        self.assertFalse(s["eligible"])

    def test_carte_threshold_per_star(self):
        s1 = compute_scores(REF, PROFILE, 1, ALL_OK)
        self.assertEqual(s1["o"]["base_required"], 1)
        s2 = compute_scores(REF, PROFILE, 2, ALL_OK)
        self.assertEqual(s2["o"]["base_required"], 3)
        s5 = compute_scores(REF, PROFILE, 5, ALL_OK)
        self.assertTrue(s5["eligible"])

    def test_star5_turns_c4_into_obligatory(self):
        appl = applicable_criteria(REF, PROFILE, 5)
        c4 = [a for a in appl if a["id"] == "C4"][0]
        self.assertEqual(c4["code"], "X")

    def test_reachable_stars(self):
        st = dict(ALL_OK)
        st["C6"] = {"status": "NON_COMPLIANT"}
        r = reachable_stars(REF, PROFILE, st)
        self.assertTrue(r[3])
        self.assertEqual(set(r.keys()), {1, 2, 3, 4, 5})


if __name__ == "__main__":
    unittest.main()
