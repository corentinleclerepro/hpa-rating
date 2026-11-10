from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from hpa_shared.http import endpoint, error, payload
from hpa_shared.registry import registry, now_iso, canonical, digest, throttled, limited


def guest_from(request):
    identity = request.session.get("guest")
    if not identity:
        return None
    db = registry()
    with db.atomic():
        return active_guest(request, db, identity)


def active_guest(request, db, identity):
    row = db.conn.execute("SELECT id,label,version,last_seen FROM guests WHERE id=? AND version=? AND revoked=0", identity).fetchone()
    if not row:
        request.session.pop("guest", None)
        return None
    if not row["last_seen"] or row["last_seen"][:16] != now_iso()[:16]:
        db.conn.execute("UPDATE guests SET last_seen=? WHERE id=?", (now_iso(), row["id"]))
    return dict(row)


@ensure_csrf_cookie
@endpoint(["GET"])
def session_info(request):
    guest = guest_from(request)
    return JsonResponse({"guest": {"label": guest["label"]} if guest else None})


@endpoint(["POST"])
def guest_login(request):
    data = payload(request)
    failure = authenticate_code(request, data.get("code", ""))
    return failure if failure is not None else JsonResponse({"ok": True})


def authenticate_code(request, code):
    db = registry()
    with db.atomic():
        bucket = throttled(db, request, "invité")
        if not bucket:
            return limited()
        row = db.conn.execute("SELECT id,version FROM guests WHERE digest=? AND revoked=0",
                              (digest("invite", canonical(code)),)).fetchone()
        if not row:
            return error("Code invalide ou révoqué.", 401)
        db.conn.execute("DELETE FROM login_limits WHERE bucket=?", (bucket,))
        db.conn.execute("UPDATE guests SET last_seen=?,code_used=1 WHERE id=?", (now_iso(), row["id"]))
        request.session.cycle_key()
        request.session["guest"] = [row["id"], row["version"]]
    return None


@endpoint(["POST"])
def guest_logout(request):
    request.session.flush()
    return JsonResponse({"ok": True})
