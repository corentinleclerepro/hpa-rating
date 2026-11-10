"""Verify the public entry without using a real invitation or touching a dossier."""
import argparse
import http.client
from http.cookies import SimpleCookie
import pathlib
import socket
import ssl
from urllib.parse import urlsplit


def verify(origin, *, connect_to=None, ca_file=None, http_port=80, tls_connect_port=None):
    url = urlsplit(origin)
    if (url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("Une origine HTTPS sans chemin est requise.")
    origin = "https://" + url.netloc
    def require(ok, message):
        if not ok:
            raise RuntimeError(message)
    plain = http.client.HTTPConnection(connect_to or url.hostname, http_port, timeout=10)
    try:
        plain.request("GET", "/connexion", headers={"Host": url.hostname})
        redirect = plain.getresponse()
        require(redirect.status in (301, 308) and redirect.getheader("Location") == origin + "/connexion",
                f"Redirection HTTP inattendue : {redirect.status}, {redirect.getheader('Location')!r}.")
    finally:
        plain.close()
    context = ssl.create_default_context(cafile=ca_file)
    def request(path, method="GET", body=None, cookie=None):
        # SNI and certificate validation always use the real public hostname.
        conn = http.client.HTTPConnection(url.hostname, url.port or 443, timeout=10)
        try:
            raw = socket.create_connection((connect_to or url.hostname, tls_connect_port or url.port or 443), timeout=10)
            conn.sock = context.wrap_socket(raw, server_hostname=url.hostname)
            headers = {"Host":url.netloc}
            if cookie:
                headers["Cookie"] = cookie
            if body is not None:
                headers.update({"Origin":origin,"Content-Type":"application/json"})
            conn.request(method,path,body=body,headers=headers)
            reply = conn.getresponse()
            return reply.status, reply.read(), reply.headers
        finally:
            conn.close()
    status, homepage, _ = request("/")
    require(status == 200 and b'action="/demande-acces#acces"' in homepage and b'href="/connexion"' in homepage,
            "La vitrine et son formulaire ne sont pas disponibles.")
    status, page, headers = request("/connexion")
    require(status == 200 and b"Hpa Rating" in page, "La page de connexion Hpa Rating n’est pas servie.")
    cookies = SimpleCookie()
    for value in headers.get_all("Set-Cookie", []):
        cookies.load(value)
    require(cookies.get("hpa_csrf") and cookies["hpa_csrf"]["secure"], "Cookie de connexion non sécurisé.")
    require(headers.get("Strict-Transport-Security"), "En-tête HSTS absent.")
    require(request("/api/audits")[0] == 401, "Les dossiers doivent exiger une invitation.")
    # A well-formed but nonexistent session makes Django consult its actual session store.
    require(request("/api/audits", cookie="hpa_session=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")[0] == 401,
            "La vérification de session côté serveur ne répond pas normalement.")
    for path in ("/administration","/api/admin/invitations","/api/admin/demandes","/static/console.js"):
        require(request(path)[0] == 404, "La console est exposée : " + path)
    require(request("/api/login","POST",b"{}")[0] == 403, "La protection CSRF ne répond pas.")
    print("Redirection HTTP, certificat TLS, page Hpa Rating, cookies sécurisés, dossiers privés et console absente : OK.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("--connect-to", help="Tester l’adresse du serveur avant de basculer le DNS")
    parser.add_argument("--ca-file",type=pathlib.Path,help="Autorité de la recette locale uniquement")
    args = parser.parse_args()
    verify(args.origin, connect_to=args.connect_to, ca_file=args.ca_file)
