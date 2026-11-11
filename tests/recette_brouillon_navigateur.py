"""Run the browser journey against two fresh local servers. Requires Node and playwright-core."""
from contextlib import ExitStack
import json
from pathlib import Path
import secrets
import subprocess

from http_fixture import PrivateServer


if __name__ == "__main__":
    with ExitStack() as cleanup:
        class Cleanup:
            addClassCleanup = staticmethod(cleanup.callback)

        server = PrivateServer(Cleanup)
        data = {"guest":"http://127.0.0.1:"+str(server.port), "admin":"http://127.0.0.1:"+str(server.admin_port),
                "profile":str(Path(server.storage.name)/"chrome-profile"), "password":secrets.token_urlsafe(32),
                "ticket":server.ticket, "mail":str(Path(server.storage.name)/"test-mail")}
        subprocess.run(["node", str(Path(__file__).with_name("brouillon_navigateur.cjs"))],
                       input=json.dumps(data), encoding="utf8", check=True, timeout=150)
