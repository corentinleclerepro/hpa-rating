import io
import json
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http_fixture import Browser, PrivateServer


class TestJustificatifsHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = PrivateServer(cls)
        cls.client = Browser(cls.server.port).enter(cls.server.guest_code)

    def request(self, *args, **kwargs):
        return self.client.call(*args, **kwargs)

    def setUp(self):
        audit = self.request("POST", "/api/audits", {"name":"Essai local", "target_stars":3}, expected=201)["audit"]
        self.root = "/api/audits/" + audit["id"]
        self.item = self.root + "/items/17"
        self.client.reach(self.root, "17")

    def upload(self, payload):
        body = (b'--hpa-test\r\nContent-Disposition: form-data; name="files"; filename="preuve.pdf"\r\n'
                b"Content-Type: application/pdf\r\n\r\n" + payload + b"\r\n--hpa-test--\r\n")
        return self.request("POST", self.item + "/evidence", expected=201, body=body,
                            mime="multipart/form-data; boundary=hpa-test")["evidences"][0]

    def test_fichiers_homonymes_concurrents_et_octets_conserves(self):
        removed = self.upload(b"premier")
        original = b"\r\n%PDF-1.4\ntexte--hpa-test-interne\x00\xff--\r\n"
        second = self.upload(original)
        self.request("DELETE", "/api/evidence/" + removed["id"])
        with ThreadPoolExecutor(max_workers=3) as pool:
            others = list(pool.map(self.upload, [b"A", b"B", b"C"]))
        proofs = [second, *others]
        self.assertEqual(len({proof["filename"] for proof in proofs}), 4)
        for ev, contents in zip(proofs, [original, b"A", b"B", b"C"]):
            self.assertEqual(self.request("GET", self.root + "/evidence/" + ev["id"] + "/file"), contents)
        self.client.reach(self.root,"summary")
        with zipfile.ZipFile(io.BytesIO(self.request("GET", self.root + "/export/zip"))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read(next(n for n in archive.namelist() if n.endswith(second["filename"]))), original)
            manifest = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith("manifest.json"))))
            self.assertEqual(len(next(c for c in manifest["criteres"] if c["id"] == "17")["evidences"]), 4)

    def test_legende_marquage_et_derniere_preuve(self):
        delta = {"status":"VALIDATED","notes":"Note à conserver","validated_by":"Test"}
        self.request("PUT", self.item, delta, expected=422)
        pdf = self.upload(b"PDF")
        url = self.request("POST", self.item + "/evidence/url", {"url":"https://example.invalid/preuve"}, expected=201)["evidence"]
        self.request("PUT", self.item, delta)
        path = "/api/evidence/" + pdf["id"]
        self.request("PATCH", path, {"caption":"Après visite"})
        updated = self.request("PATCH", path, {"stale":1})["evidence"]
        self.assertEqual((updated["stale"], updated["caption"]), (1, "Après visite"))
        reset = self.request("PATCH", path, {"stale":0})["evidence"]
        self.assertEqual((reset["stale"], reset["caption"]), (0, "Après visite"))
        self.request("DELETE", path)
        before = self.request("GET", self.root + "/score")["score"]
        self.assertEqual(before["x"]["obtained"], 3)
        self.request("DELETE", "/api/evidence/" + url["id"])
        saved = self.request("GET", self.root)["items"]["17"]
        self.assertEqual((saved["status"],saved["notes"],saved["validated_at"]), ("EVIDENCE_MISSING","Note à conserver",None))
        self.assertEqual(self.request("GET", self.root + "/score")["score"]["x"]["obtained"], 0)
        self.client.reach(self.root,"summary")
        book = self.request("GET", self.root + "/export/book").decode()
        self.assertIn("Preuve manquante", book)
        self.assertIn("Note à conserver", book)
        self.upload(b"nouvelle piece")
        self.assertEqual(self.request("GET", self.root)["items"]["17"]["status"], "EVIDENCE_MISSING")

    def test_bonification_par_api_clonage_et_exports(self):
        path = self.root + "/items/22"
        self.client.reach(self.root,"22")
        self.request("PUT", path, {"status":"VALIDATED"}, expected=400)
        self.request("PUT", path, {"status":"VALIDATED","awarded_points":6}, expected=400)
        self.request("PUT", path, {"status":"VALIDATED","awarded_points":2})
        clone = self.request("POST", self.root + "/clone", {}, expected=201)["audit"]
        root = "/api/audits/" + clone["id"]
        self.assertEqual(self.request("GET", root + "/score")["score"]["o"]["obtained"], 2)
        self.client.reach(root,"summary")
        self.assertIn("Bonification obtenue : 2 pt", self.request("GET", root + "/export/book").decode())
