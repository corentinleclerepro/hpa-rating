from pathlib import Path
from django.http import FileResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from .http import endpoint

SHARED = Path(__file__).parent / "static"
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".css": "text/css", ".js": "text/javascript"}


def frontend(static, names):
    files = {name: static / name for name in names}
    files.update({name: SHARED / name for name in ("brand.css", "common.js", "logo.png")})

    @ensure_csrf_cookie
    @endpoint(["GET"])
    def page(request):
        return FileResponse((static / "index.html").open("rb"), content_type="text/html; charset=utf-8")

    @endpoint(["GET"])
    def asset(request, name):
        if name not in files:
            raise FileNotFoundError
        return FileResponse(files[name].open("rb"), content_type=TYPES[files[name].suffix])

    return page, asset
