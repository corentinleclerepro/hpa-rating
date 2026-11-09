import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from http_fixture import Browser, PrivateServer


class ParcoursGuide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = PrivateServer(cls)
        cls.guest = Browser(cls.server.port).enter(cls.server.guest_code)

    def test_ordre_brouillon_non_applicable_et_reprise(self):
        call = self.guest.call
        audit = call("POST","/api/audits",{"name":"Étapes","target_stars":3},expected=201)["audit"]
        root = "/api/audits/" + audit["id"]
        self.assertEqual(call("GET",root)["audit"]["workflow"]["open_steps"], ["profile"])
        call("PUT",root+"/items/1",{"status":"VALIDATED"},expected=409)
        call("POST",root+"/items/1/evidence/url",{"url":"https://example.org/test"},expected=409)
        call("PATCH",root,{"confirm_profile":True,"profile":{"nb_emplacements":0}},expected=422)
        self.assertEqual(call("PATCH",root,{"profile":{"nb_emplacements":60}})["audit"]["workflow"]["current"],"profile")
        f = call("PATCH",root,{"confirm_profile":True})["audit"]["workflow"]
        self.assertEqual((f["current"], f["next_id"], f["allowed_ids"]), ("prerequisites","1",["1"]))
        call("PUT",root+"/resume",{"criterion_id":"2"},expected=409)
        call("PUT",root+"/items/1",{"status":"TODO","notes":"à mesurer","advance":True},expected=422)
        call("PUT",root+"/items/1",{"status":"TODO","notes":"à mesurer"})
        self.assertEqual(call("GET",root)["items"]["1"]["notes"], "à mesurer")
        f = call("PUT",root+"/items/1",{"status":"NON_COMPLIANT","advance":True})["workflow"]
        self.assertEqual(f["next_id"], "2")
        call("POST",root+"/review-proofs",{"reviewed":True},expected=409)
        call("PUT",root+"/items/2",{"status":"VALIDATED","advance":True},expected=422)
        f = call("PUT",root+"/items/2",{"status":"EVIDENCE_MISSING","advance":True})["workflow"]
        self.assertEqual(f["current"],"criteria")
        self.assertNotIn("3", f["allowed_ids"])  # PRL-only prerequisite
        applicable=[c["id"] for c in call("GET",root+"/criteria")["criteria"] if c["chapter"]!=0 and c["code"]!="NA"]
        self.assertEqual(f["next_id"], applicable[0])
        call("PUT",root+"/items/"+applicable[1],{"status":"VALIDATED"},expected=409)
        call("GET",root+"/export/zip",expected=409)
        call("GET",root+"/score?stars=4",expected=409)
        self.assertNotIn("eligible",call("GET",root+"/score")["score"])
        visitor=Browser(self.server.port).enter(self.server.guest_code)
        self.assertEqual(visitor.call("GET",root)["audit"]["workflow"]["next_id"],applicable[0])
        f=visitor.call("PUT",root+"/items/"+applicable[0],{"status":"IN_PROGRESS","advance":True})["workflow"]
        self.assertEqual(f["next_id"],applicable[1])
        # Reopening an earlier item immediately relocks later entries, without deleting them.
        f=call("PUT",root+"/items/1",{"status":"TODO"})["workflow"]
        self.assertEqual((f["current"],f["next_id"]),("prerequisites","1"))
        call("PUT",root+"/items/"+applicable[0],{"status":"TODO"},expected=409)
        f=call("PUT",root+"/items/1",{"status":"IN_PROGRESS"})["workflow"]
        self.assertEqual(f["next_id"],applicable[1])
        self.assertEqual(call("GET",root)["items"][applicable[0]]["status"],"IN_PROGRESS")

    def test_pieces_existantes_protegees_et_revue_explicite(self):
        call=self.guest.call
        aid=call("POST","/api/audits/demo",{},expected=201)["audit"]["id"]
        root="/api/audits/"+aid
        info=call("GET",root)
        self.assertEqual((info["audit"]["filled"], info["evidence_count"]), (7,3))
        # A guessed URL, or one bookmarked before the migration, cannot bypass the order.
        with closing(sqlite3.connect(Path(self.server.storage.name)/"app.db")) as con:
            pid=con.execute("SELECT id FROM evidences WHERE audit_id=? AND criterion_id='21'",(aid,)).fetchone()[0]
        url=root+"/evidence/"+pid+"/file"
        call("GET",url,expected=409)
        call("PATCH","/api/evidence/"+pid,{"caption":"saut"},expected=409)
        call("DELETE","/api/evidence/"+pid,{},expected=409)
        call("POST",root+"/items/21/evidence/url",{"url":"https://example.org/saute"},expected=409)
        self.guest.reach(root,"proofs")
        self.assertTrue(call("GET",url).startswith(b"%PDF"))
        call("GET",root+"/export/book",expected=409)
        call("POST",root+"/review-proofs",{"reviewed":False},expected=422)
        f=call("POST",root+"/review-proofs",{"reviewed":True})["workflow"]
        self.assertEqual(f["current"],"summary")
        self.assertFalse(call("GET",root+"/score")["score"]["eligible"])
        self.assertIn(b"<html",call("GET",root+"/export/book"))
        call("PATCH","/api/evidence/"+pid,{"stale":1})
        self.assertEqual(call("GET",root)["audit"]["workflow"]["current"],"proofs")
        call("GET",root+"/export/zip",expected=409)
