"""Exercise the real production processes with separate stores and a simulated TLS upstream."""
import base64
from contextlib import ExitStack
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from django_otp.oath import totp


ROOT = Path(__file__).resolve().parents[1]
SITE = "hpa-rating.campcompagnon.fr"
ORIGIN = "https://" + SITE


class Visitor:
    def __init__(self, port, *, public=False):
        self.port, self.public = port, public
        self.cookies = SimpleCookie()

    def call(self, method, path, body=None, *, expected=200, origin=None, host=None, secure=True):
        headers = {"Host": host or (SITE if self.public else "127.0.0.1:" + str(self.port))}
        if self.public and secure:
            headers.update({"X-Forwarded-Proto": "https", "X-Forwarded-For": "192.0.2.55"})
        for key, value in self.cookies.items():
            if key.endswith("csrf"):
                headers["X-CSRFToken"] = value.value
        headers["Cookie"] = "; ".join(f"{k}={v.value}" for k, v in self.cookies.items())
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Origin"] = origin or (ORIGIN if self.public else "http://" + headers["Host"])
            body = json.dumps(body).encode()
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            reply = conn.getresponse()
            content = reply.read()
            assert reply.status == expected, (method, path, reply.status, expected)
            for key, value in reply.getheaders():
                if key.lower() == "set-cookie":
                    self.cookies.load(value)
            return (json.loads(content) if "json" in reply.getheader("Content-Type", "") else content), dict(reply.getheaders())
        finally:
            conn.close()


@unittest.skipUnless(importlib.util.find_spec("waitress"), "Installer requirements-production.txt pour cette recette")
class PublicHttps(unittest.TestCase):
    def test_public_private_persistence_and_codes(self):
        with ExitStack() as stack:
            state = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            env = {**os.environ, "HPA_ENV": "production", "HPA_GUEST_ORIGIN": ORIGIN,
                   "HPA_REGISTRY_DIR": str(state/"invitations"), "PYTHONIOENCODING":"utf-8"}
            env.pop("HPA_HTTPS", None)
            def role_env(role):
                return {**env, "HPA_DATA_DIR": str(state/role)}
            def start(role):
                proc = subprocess.Popen([sys.executable, "-B", "run_production.py", role, "--port", "0"],
                                        env=role_env(role), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding="utf-8")
                def stop():
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=8)
                    proc.stdout.close()
                stack.callback(stop)
                line = proc.stdout.readline()
                self.assertTrue(line.startswith(f"{role}: http://127.0.0.1:"), line)
                return Visitor(int(line.rsplit(":", 1)[1]), public=role == "guest"), stop
            ticket = state/"setup.txt"
            subprocess.run([sys.executable, "-B","run_admin.py","--setup-key",str(ticket)], env=role_env("admin"),
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            admin, _ = start("admin")
            guest, stop_guest = start("guest")
            _, headers = guest.call("GET","/connexion", secure=False, expected=301)
            self.assertEqual(headers.get("Location"), ORIGIN + "/connexion")
            _, headers = guest.call("GET","/connexion")
            self.assertIn("max-age=", headers["Strict-Transport-Security"])
            self.assertTrue(guest.cookies["hpa_csrf"]["secure"])
            guest.call("GET","/espace",host="other.example",expected=400)
            for url in ("/administration","/api/admin/invitations","/static/console.js"):
                guest.call("GET", url, expected=404)
            admin.call("GET","/",host=SITE,expected=400)
            admin.call("GET","/api/audits",expected=404)
            guest.call("GET","/api/audits",expected=401)
            admin.call("GET","/api/session")
            auth, _ = admin.call("POST","/api/admin/setup/start",{"ticket":ticket.read_text("utf-8-sig").splitlines()[-1],
                                                                  "password":"Seulement pour cet essai HTTPS ! 819"})
            admin.call("POST","/api/admin/setup/finish",{"otp":str(totp(base64.b32decode(auth["manual_key"]))).zfill(6)})
            first, _ = admin.call("POST","/api/admin/invitations",{"label":"Essai HTTPS jetable"},expected=201)
            self.assertEqual(first["login_url"], ORIGIN + "/connexion")
            guest.call("POST","/api/login",{"code":first["code"]},origin="https://autre.example",expected=403)
            guest.call("POST","/api/login",{"code":first["code"]})
            self.assertTrue(guest.cookies["hpa_session"]["secure"] and guest.cookies["hpa_session"]["httponly"])
            dossier, _ = guest.call("POST","/api/audits/demo",{},expected=201)
            aid = dossier["audit"]["id"]
            stop_guest()
            previous = guest.cookies
            guest, _ = start("guest")
            guest.cookies = previous
            same, _ = guest.call("GET", "/api/audits/" + aid)
            self.assertEqual(same["evidence_count"], 3)
            admin.call("POST", "/api/admin/invitations/" + first["id"] + "/revoke", {})
            guest.call("GET", "/api/audits/"+aid, expected=401)
            self.assertFalse((state/"admin"/"dossiers").exists())
            self.assertFalse((state/"guest"/"access.sqlite3").exists())
            self.assertEqual({p.name for p in (state/"invitations").iterdir()}, {"invitations.sqlite3","invitation.key"})
            self.assertNotEqual((state/"admin"/"application.key").read_bytes(), (state/"guest"/"application.key").read_bytes())
            key_file = state/"invitations"/"invitation.key"
            key_file.rename(state/"key-held-for-restore")
            restart = subprocess.run([sys.executable, "-B", "-c", "import hpa_shared.settings"],
                                     env=role_env("guest"), cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(restart.returncode, 0)
            self.assertIn("Clé manquante (invitation.key)", restart.stderr)
            self.assertFalse(key_file.exists(), "Un registre restauré ne doit pas recevoir une nouvelle clé.")
