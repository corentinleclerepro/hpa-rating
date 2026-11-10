from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from django import forms
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.template import Context, Engine
from django.views.decorators.http import require_http_methods
from hpa_shared.registry import now_iso, registry, throttled


class AccessRequestForm(forms.Form):
    camping = forms.CharField(max_length=140)
    email = forms.EmailField(max_length=254)
    website = forms.CharField(required=False)


@lru_cache(maxsize=1)
def landing_template():
    return Engine(dirs=[Path(__file__).parent / "static"]).get_template("landing.html")


def render_page(request, form=None, message="", status=200):
    context = {"csrf_token": get_token(request), "received": request.GET.get("demande") == "recue",
               "message": message, "form": form}
    return HttpResponse(landing_template().render(Context(context)), status=status)


@require_http_methods(["GET", "HEAD"])
def home(request):
    return render_page(request)


@require_http_methods(["POST"])
def request_access(request):
    if int(request.META.get("CONTENT_LENGTH") or 0) > 8192:
        return HttpResponse(status=413)
    form = AccessRequestForm(request.POST)
    if not form.is_valid():
        return render_page(request, form, "Vérifiez le nom du camping et l’adresse e-mail.", 400)
    result = HttpResponseRedirect("/?demande=recue#acces")
    result.status_code = 303
    if form.cleaned_data["website"]:
        return result
    camping = form.cleaned_data["camping"]
    email = form.cleaned_data["email"].lower()
    db = registry()
    with db.atomic():
        if not throttled(db, request, "demande-acces"):
            response = render_page(request, form, "Trop de demandes. Réessayez dans dix minutes.", 429)
            response["Retry-After"] = "600"
            return response
        values = (uuid4().hex, camping, email, now_iso())
        if settings.CLOUD_ROLE:
            db.conn.execute("SELECT hpa_rating.submit_access_request(?,?,?,?)", values)
        else:
            db.conn.execute("""INSERT INTO access_requests(id,camping,email,created_at)
                               VALUES(?,?,?,?) ON CONFLICT DO NOTHING""", values)
    return result
