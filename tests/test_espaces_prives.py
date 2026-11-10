import base64
import io
import unittest
import zipfile
from urllib.parse import urlencode
from pathlib import Path
from django_otp.oath import totp
from http_fixture import Browser, PrivateServer


class EspacesPrives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=PrivateServer(cls)
        cls.admin=Browser(cls.server.admin_port, console=True)
        cls.admin.call("GET","/api/session")
        password="Un essai de classement ! 319"
        proof=cls.admin.call("POST","/api/admin/setup/start",{"ticket":cls.server.ticket,"password":password})
        cls.key=base64.b32decode(proof["manual_key"])
        assert proof["qr"].startswith("data:image/svg+xml;base64,")
        cls.admin.call("POST","/api/admin/setup/finish",{"otp":"impossible"},expected=401)
        reply=cls.admin.call("POST","/api/admin/setup/finish",{"otp":str(totp(cls.key)).zfill(6)})
        cls.backups=reply["recovery_codes"]
        assert len(cls.backups)==8
        cls.password=password

    def invite(self,label):
        obj=self.admin.call("POST","/api/admin/invitations",{"label":label},expected=201)
        self.assertEqual(obj["login_url"], self.server.guest_origin + "/connexion")
        return obj,Browser(self.server.port).enter(obj["code"])

    def test_vitrine_demande_et_decision(self):
        visitor = Browser(self.server.port)
        self.assertIn(b'action="/demande-acces#acces"', visitor.call("GET", "/"))
        for name in ("clairiere.jpg", "preparation.jpg"):
            self.assertTrue(visitor.call("GET", "/static/"+name).startswith(b"\xff\xd8"))
        def send(email, **options):
            fields = {"camping": "La Pinède", "email": email, "website": ""}
            return visitor.call("POST", "/demande-acces", mime="application/x-www-form-urlencoded",
                                body=urlencode(fields).encode(), **options)
        self.assertIn("La Pinède".encode(), send("invalide", expected=400))
        send("camping@example.test", csrf=False, expected=403)
        send("Camping@Example.test", expected=303)
        send("camping@example.test", expected=303)
        listing = "/api/admin/demandes"
        visitor.call("GET", listing, expected=404)
        Browser(self.server.admin_port, console=True).call("GET", listing, expected=403)
        rows = self.admin.call("GET", listing)["requests"]
        matches = [r for r in rows if r["email"] == "camping@example.test"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "pending")
        decision = listing + "/" + matches[0]["id"] + "/approve"
        issued = self.admin.call("POST", decision, {}, expected=201)
        self.admin.call("POST", decision, {}, expected=409)
        guest = Browser(self.server.port).enter(issued["code"])
        self.assertEqual(guest.call("GET", "/api/session")["guest"]["label"], "La Pinède")
        send("camping@example.test", expected=303)
        send("refus@example.test", expected=303)
        rows = self.admin.call("GET", listing)["requests"]
        self.assertEqual(len([r for r in rows if r["email"] == issued["email"]]), 1)
        refused = next(r for r in rows if r["email"] == "refus@example.test")
        self.admin.call("POST", listing+"/"+refused["id"]+"/decline", {})
        decided = self.admin.call("GET", listing)["requests"]
        self.assertFalse(any(r["id"] == refused["id"] or r["email"] == refused["email"] for r in decided))
        self.assertTrue(any(r["id"] == matches[0]["id"] and r["status"] == "approved" for r in decided))
        self.admin.call("POST", listing+"/"+refused["id"]+"/approve", {}, expected=404)

    def test_demo_publique_sans_session_et_sans_fichier_prive(self):
        first, second = Browser(self.server.port), Browser(self.server.port)
        def counters(client, query, expected):
            page = client.call("GET", "/demo" + query).decode()
            for name, value in zip(("filled", "mandatory", "optional"), expected):
                self.assertRegex(page, rf'<dd id="{name}">{value}(?: |<)')
            return page
        initial = counters(first, "", (7, 4, 3))
        self.assertIn('/ 192</small>', initial)
        counters(first, "?statut=en-cours", (8, 4, 3))
        counters(first, "?statut=valide", (8, 7, 3))
        counters(second, "", (7, 4, 3))
        counters(first, "", (7, 4, 3))
        self.assertEqual(first.cookies, {})
        for filename in ("releve-surfaces.pdf", "plan-reperage.pdf", "fiche-location-velos.pdf"):
            path = "/demo/justificatifs/" + filename
            self.assertIn(path, initial)
            self.assertTrue(first.call("GET", path).startswith(b"%PDF-"))
            preview = "/static/demo-" + filename.removesuffix(".pdf") + ".png"
            self.assertIn(preview, initial)
            self.assertTrue(first.call("GET", preview).startswith(b"\x89PNG"))
        first.call("GET", "/demo/justificatifs/camping.json", expected=404)
        first.call("GET", "/demo?statut=inconnu", expected=404)
        first.call("GET", "/api/audits", expected=401)

    def test_connexion_html_et_liens_publics(self):
        browser = Browser(self.server.port)
        page = browser.call("GET", "/connexion")
        self.assertIn(b'name="code"', page)
        self.assertIn(b'J\xe2\x80\x99ai perdu mon code', page)
        for path in ("/mentions-legales", "/confidentialite", "/cgu", "/demo"):
            self.assertIn(path.encode(), page)
            self.assertIn(path.encode(), browser.call("GET", "/sitemap.xml"))
        self.assertNotIn(b"/espace", browser.call("GET", "/sitemap.xml"))
        origin = "http://127.0.0.1:" + str(self.server.port)
        browser.call("POST", "/connexion", body=urlencode({"code": self.server.guest_code}).encode(),
                     mime="application/x-www-form-urlencoded", expected=303, origin=origin)
        self.assertIsNotNone(browser.call("GET", "/api/session")["guest"])

    def test_admin_second_facteur_et_codes_de_secours(self):
        anon=Browser(self.server.admin_port, console=True)
        anon.call("GET","/api/session")
        anon.call("POST","/api/admin/login",{"password":self.password,"otp":"invalide"},expected=401)
        code=self.backups[0]
        anon.call("POST","/api/admin/login",{"password":self.password,"otp":code})
        self.assertTrue(anon.call("GET","/api/session")["admin"])
        anon.call("GET","/api/audits",expected=404)
        anon.call("POST","/api/logout/admin",{})
        anon.call("GET","/api/session")
        anon.call("POST","/api/admin/login",{"password":self.password,"otp":code},expected=401)

    def test_espaces_pieces_exports_et_suppression(self):
        _,a=self.invite("Camping A")
        _,b=self.invite("Camping B")
        a.call("GET","/api/admin/invitations",expected=404)
        dossier=a.call("POST","/api/audits/demo",{},expected=201)["audit"]
        other=b.call("POST","/api/audits/demo",{},expected=201)["audit"]
        self.assertNotEqual(dossier["id"],other["id"])
        root="/api/audits/"+dossier["id"]
        info=a.call("GET",root)
        self.assertEqual((info["audit"]["filled"],info["evidence_count"]),(7,3))
        score=a.call("GET",root+"/score")["score"]
        self.assertEqual((score["x"]["obtained"],score["x"]["total"],score["o"]["obtained"]),(4,192,3))
        a.reach(root,"17")
        proof=a.call("GET",root)["evidences"][0]
        path=root+"/evidence/"+proof["id"]+"/file"
        for url in [root,path,root+"/export/zip",root+"/export/book",root+"/criteria",root+"/score"]:
            b.call("GET",url,expected=404)
            Browser(self.server.port).call("GET",url,expected=401)
        for method,url,body in [("PATCH","/api/evidence/"+proof["id"],{"caption":"interdit"}),("DELETE","/api/evidence/"+proof["id"],{}),
                                 ("POST",root+"/clone",{}),("DELETE",root,{"confirm_name":dossier["name"]}),("PUT",root+"/resume",{"criterion_id":"17"})]:
            b.call(method,url,body,expected=404)
        self.assertEqual([r["id"] for r in b.call("GET","/api/audits")["audits"]],[other["id"]])
        self.assertTrue(a.call("GET",path).startswith(b"%PDF"))
        b.call("PATCH","/api/audits/"+other["id"]+"/items/17",{},expected=405)
        b.reach("/api/audits/"+other["id"],"17")
        b.call("PUT","/api/audits/"+other["id"]+"/items/17",{"status":"IN_PROGRESS","notes":"Note privée de B"})
        for browser,aid,marker in [(a,dossier["id"],False),(b,other["id"],True)]:
            browser.reach("/api/audits/"+aid,"summary")
            with zipfile.ZipFile(io.BytesIO(browser.call("GET","/api/audits/"+aid+"/export/zip"))) as z:
                manifest=z.read(next(k for k in z.namelist() if k.endswith("manifest.json"))).decode()
                self.assertEqual("Note privée de B" in manifest,marker)
                self.assertEqual(len([k for k in z.namelist() if k.endswith(".pdf")]),3)
        a.call("DELETE",root,{"confirm_name":"erreur"},expected=400)
        a.call("DELETE",root,{"confirm_name":dossier["name"]})
        a.call("GET",path,expected=404)
        self.assertFalse((Path(self.server.storage.name)/"dossiers"/dossier["id"]).exists())
        self.assertEqual(len(b.call("GET","/api/audits/"+other["id"])["evidences"]),3)

    def test_rotation_reprise_simulation_et_revocation(self):
        invite,a=self.invite("Rotation")
        dossier=a.call("POST","/api/audits/demo",{},expected=201)["audit"]
        root="/api/audits/"+dossier["id"]
        a.reach(root,"summary")
        a.call("PUT",root+"/resume",{"criterion_id":"17","stars":3})
        self.assertFalse(a.call("PUT",root+"/resume",{"criterion_id":"21","stars":4})["saved"])
        self.assertEqual(a.call("GET",root+"/score?stars=4")["score"]["x"]["obtained"],3)
        new=self.admin.call("POST","/api/admin/invitations/"+invite["id"]+"/rotate",{},expected=201)
        listed=self.admin.call("GET","/api/admin/invitations")["guests"]
        rotated=next(row for row in listed if row["id"]==invite["id"])
        self.assertEqual(rotated["code_used"],0)
        self.assertIsNotNone(rotated["last_seen"])
        a.call("GET",root,expected=401)
        a.call("POST","/api/login",{"code":invite["code"]},expected=401)
        a.enter(new["code"])
        self.assertEqual(a.call("GET",root)["audit"]["resume_criterion"],"17")
        self.assertEqual(a.call("GET",root)["audit"]["target_stars"],3)
        a.call("PATCH",root,{"name":"refus CSRF"},csrf=False,expected=403)
        a.call("PATCH",root,{"name":"Parc du soir"})
        self.assertIn("Profil",a.call("GET",root)["history"][0]["message"])
        listed=self.admin.call("GET","/api/admin/invitations")["guests"]
        self.assertNotIn(new["code"],str(listed))
        self.admin.call("POST","/api/admin/invitations/"+invite["id"]+"/revoke",{})
        a.call("GET",root,expected=401)

    def test_limitation_codes_invites(self):
        anon=Browser(self.server.port)
        anon.call("GET","/api/session")
        for _ in range(10):
            anon.call("POST","/api/login",{"code":"non-valide"},expected=401)
        anon.call("POST","/api/login",{"code":"non-valide"},expected=429)
        # Release only the rate limiter of this isolated test server for the next case.
        import sqlite3
        with sqlite3.connect(Path(self.server.storage.name)/"invitations.sqlite3") as con:
            con.execute("DELETE FROM login_limits")
        con.close()

    def test_frontieres_des_deux_services(self):
        _,guest=self.invite("Séparation")
        admin=self.admin
        self.assertEqual(set(guest.call("GET","/api/session")), {"guest"})
        self.assertEqual(set(admin.call("GET","/api/session")), {"admin","setup_required"})
        for url in ("/administration","/admin","/api/admin/invitations","/api/admin/login","/api/admin/setup/start",
                    "/api/admin/setup/finish","/api/logout/admin","/static/console.js","/static/console.css"):
            guest.call("GET",url,expected=404)
        guest.call("POST","/api/admin/invitations",{"label":"non"},expected=404)
        d=guest.call("POST","/api/audits/demo",{},expected=201)["audit"]["id"]
        guest.reach("/api/audits/"+d, "17")
        proof=guest.call("GET","/api/audits/"+d)["evidences"][0]["id"]
        for url in ("/espace","/connexion","/api/login","/api/audits","/static/workspace.js","/api/logout/guest",
                    f"/api/audits/{d}/evidence/{proof}/file",f"/api/audits/{d}/export/zip",f"/api/audits/{d}/export/book"):
            admin.call("GET",url,expected=404)
        admin.call("POST","/api/admin/invitations",{"label":"depuis l’autre origine"},origin=self.server.guest_origin,expected=403)
        # Even a copied session ID under the other service's cookie name has no authority.
        stranger=Browser(self.server.admin_port,console=True)
        stranger.cookies["hpa_console_session"]=guest.cookies["hpa_session"]
        self.assertFalse(stranger.call("GET","/api/session")["admin"])
        stranger.call("GET","/api/admin/invitations",expected=403)
        stranger=Browser(self.server.port)
        stranger.cookies["hpa_session"]=admin.cookies["hpa_console_session"]
        self.assertIsNone(stranger.call("GET","/api/session")["guest"])
        stranger.call("GET","/api/audits",expected=401)
        # Logging off the guest does not terminate the operator's own session.
        guest.call("POST","/api/logout/guest",{})
        self.assertTrue(admin.call("GET","/api/session")["admin"])
