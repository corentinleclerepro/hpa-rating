"""Exercise the public HTTP entry points with real session and CSRF cookies."""
import json
import os
import re
import subprocess
import sys
import tempfile
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path


class Browser:
    def __init__(self, port, *, console=False):
        self.port = port
        self.cookies = {}
        self.csrf_cookie = "hpa_console_csrf" if console else "hpa_csrf"

    def call(self, method, path, fields=None, *, expected=200, body=None, mime=None, csrf=True, origin=None):
        if fields is not None:
            body, mime = json.dumps(fields).encode(), "application/json"
        conn = HTTPConnection("127.0.0.1", self.port, timeout=12)
        try:
            headers = {"Cookie": "; ".join(f"{k}={v}" for k,v in self.cookies.items())}
            if csrf and self.csrf_cookie in self.cookies:
                headers["X-CSRFToken"] = self.cookies[self.csrf_cookie]
            if origin:
                headers["Origin"] = origin
            if mime:
                headers["Content-Type"] = mime
            conn.request(method, path, body, headers)
            response = conn.getresponse()
            for key,val in response.getheaders():
                if key.lower() == "set-cookie":
                    cookie = SimpleCookie(val)
                    self.cookies.update({k:v.value for k,v in cookie.items()})
            content = response.read()
            assert response.status == expected, (method,path,response.status,expected,content[:380])
            return json.loads(content) if "json" in response.getheader("Content-Type","") else content
        finally:
            conn.close()

    def enter(self, code):
        self.call("GET","/api/session")
        self.call("POST","/api/login",{"code":code})
        return self

    def reach(self, root, destination):
        """Exercise the real ordered path, without inventing successful regulatory checks."""
        guide = self.call("GET", root)["audit"]["workflow"]
        for _ in range(200):
            if guide["current"] == destination or destination in guide["allowed_ids"]:
                return guide
            if guide["current"] == "profile":
                guide = self.call("PATCH", root, {"profile":{"nb_emplacements":80}, "confirm_profile":True})["audit"]["workflow"]
            elif guide["next_id"]:
                guide = self.call("PUT", root+"/items/"+guide["next_id"], {"status":"IN_PROGRESS","advance":True})["workflow"]
            elif guide["current"] == "proofs":
                guide = self.call("POST",root+"/review-proofs",{"reviewed":True})["workflow"]
            else:
                break
        raise AssertionError(("Étape inaccessible", destination, guide["current"]))


class PrivateServer:
    def __init__(self, case):
        self.storage = tempfile.TemporaryDirectory()
        case.addClassCleanup(self.storage.cleanup)
        root = Path(__file__).resolve().parents[1]
        self.env = {**os.environ,"HPA_DATA_DIR":self.storage.name,"PYTHONIOENCODING":"utf-8"}
        card = Path(self.storage.name)/"first.txt"
        cmd = [sys.executable,"-X","utf8","-B"]
        subprocess.run([*cmd,"init_local.py",str(card)],cwd=root,env=self.env,check=True,stdout=subprocess.DEVNULL)
        lines = card.read_text("utf-8-sig").splitlines()
        self.guest_code=lines[-1]
        self.ticket=lines[lines.index("Clé de première configuration (24 h) :")+1]
        def start(script, env):
            wrapper = ["tests/fixture_mail.py"] if script == "run_admin.py" else []
            proc = subprocess.Popen([*cmd,*wrapper,script,"--port","0"], cwd=root, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,text=True,encoding="utf-8")
            case.addClassCleanup(self.stop, proc)
            line = proc.stdout.readline()
            found = re.search(r"127\.0\.0\.1:(\d+)",line)
            if not found:
                raise RuntimeError("Le serveur de test ne démarre pas : "+script)
            return int(found.group(1))
        self.port = start("run.py", self.env)
        self.guest_origin = f"http://localhost:{self.port}"
        self.admin_port = start("run_admin.py", {**self.env,"HPA_GUEST_ORIGIN":self.guest_origin})

    @staticmethod
    def stop(proc):
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
