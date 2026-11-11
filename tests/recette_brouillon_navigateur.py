"""Run the browser journey against two fresh local servers. Requires Node and playwright-core."""
import base64
from contextlib import ExitStack
import json
from pathlib import Path
import secrets
import subprocess

from django_otp.oath import totp
from http_fixture import Browser, PrivateServer


if __name__ == "__main__":
    with ExitStack() as cleanup:
        class Cleanup:
            addClassCleanup = staticmethod(cleanup.callback)

        server = PrivateServer(Cleanup)
        admin = Browser(server.admin_port, console=True)
        admin.call("GET", "/api/session")
        password = secrets.token_urlsafe(32)
        setup = admin.call("POST", "/api/admin/setup/start", {"ticket":server.ticket, "password":password})
        code = str(totp(base64.b32decode(setup["manual_key"]))).zfill(6)
        recovery = admin.call("POST", "/api/admin/setup/finish", {"otp":code})["recovery_codes"][0]
        data = {"guest":"http://127.0.0.1:"+str(server.port), "admin":"http://127.0.0.1:"+str(server.admin_port),
                "profile":str(Path(server.storage.name)/"chrome-profile"), "password":password, "recovery":recovery}
        subprocess.run(["node", str(Path(__file__).with_name("brouillon_navigateur.cjs"))],
                       input=json.dumps(data), encoding="utf8", check=True, timeout=150)
