import json
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from django import forms
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.template import Context, Engine
from django.views.decorators.http import require_http_methods
from hpa_shared.registry import count_starter, now_iso, registry, throttled
from .access import authenticate_code, guest_from
from .referentiel import load, publication


public_templates = Engine(dirs=[Path(__file__).parent / "static"])
PUBLIC_PAGES = ("/", "/commencer", "/demo", "/cgu", "/mentions-legales", "/confidentialite")


class AccessRequestForm(forms.Form):
    camping = forms.CharField(max_length=140)
    email = forms.EmailField(max_length=254)
    website = forms.CharField(required=False)


def request_problem(request, form, message, status, starter_flow):
    if starter_flow:
        from .starter import public_grid
        return public_response(request, "starter.html", {"grid": public_grid(), "form": form,
            "message": message, "csrf_token": get_token(request), "form_retry": True}, status)
    return render_page(request, form, message, status)


def site_origin(request):
    return settings.GUEST_ORIGIN if settings.PRODUCTION else request.build_absolute_uri("/").rstrip("/")


def public_response(request, template, context=None, status=200):
    data = {"canonical": site_origin(request) + request.path, **(context or {})}
    response = HttpResponse(public_templates.get_template(template).render(Context(data)), status=status)
    # Native POST forms need a same-origin referrer for Django's CSRF checks.
    response["Referrer-Policy"] = "same-origin"
    return response


def render_page(request, form=None, message="", status=200):
    context = {"csrf_token": get_token(request), "received": request.GET.get("demande") == "recue",
               "message": message, "form": form, "reference": publication(load())}
    return public_response(request, "landing.html", context, status)


@require_http_methods(["GET", "HEAD"])
def home(request):
    return render_page(request)


@require_http_methods(["GET", "HEAD"])
def information(request, page):
    return public_response(request, page + ".html", {"current_page": page})


@require_http_methods(["GET", "HEAD", "POST"])
def connection(request):
    message, status = "", 200
    if request.method == "POST":
        if int(request.META.get("CONTENT_LENGTH") or 0) > 8192:
            return HttpResponse(status=413)
        failure = authenticate_code(request, request.POST.get("code", ""))
        if failure is None:
            response = HttpResponseRedirect("/espace")
            response.status_code = 303
            return response
        status = failure.status_code
        message = ("Trop de tentatives. Réessayez dans dix minutes." if status == 429
                   else "Code invalide ou révoqué. Vérifiez le code reçu par e-mail.")
    elif guest_from(request):
        return HttpResponseRedirect("/espace")
    response = public_response(request, "connection.html", {"current_page": "connection", "message": message,
                               "csrf_token": get_token(request)}, status)
    if status == 429:
        response["Retry-After"] = "600"
    response["X-Robots-Tag"] = "noindex"
    return response


@require_http_methods(["GET", "HEAD"])
def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /api/\nDisallow: /demo/justificatifs/\n"
                        f"Sitemap: {site_origin(request)}/sitemap.xml\n", content_type="text/plain; charset=utf-8")


@require_http_methods(["GET", "HEAD"])
def sitemap(request):
    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for path in PUBLIC_PAGES:
        ET.SubElement(ET.SubElement(root, "url"), "loc").text = site_origin(request) + path
    return HttpResponse(ET.tostring(root, encoding="utf-8", xml_declaration=True), content_type="application/xml")


@require_http_methods(["POST"])
def request_access(request):
    if int(request.META.get("CONTENT_LENGTH") or 0) > 8192:
        return HttpResponse(status=413)
    form = AccessRequestForm(request.POST)
    starter_flow = request.POST.get("origin") == "starter"
    if not form.is_valid():
        return request_problem(request, form, "Vérifiez le nom du camping et l’adresse e-mail.", 400, starter_flow)
    result = HttpResponseRedirect("/?demande=recue#acces")
    result.status_code = 303
    if form.cleaned_data["website"]:
        return result
    camping = form.cleaned_data["camping"]
    email = form.cleaned_data["email"].lower()
    content = None
    if starter_flow and request.POST.get("attach") == "yes":
        from .starter import checked_draft
        try:
            content = json.dumps(checked_draft(json.loads(request.POST.get("draft", ""))), separators=(",",":"))
        except (TypeError, ValueError):
            return request_problem(request, form, "Le brouillon joint est incomplet. Vérifiez les fiches ou décochez la copie.", 400, True)
    db = registry()
    with db.atomic():
        if not throttled(db, request, "demande-acces"):
            response = request_problem(request, form, "Trop de demandes. Réessayez dans dix minutes.", 429, starter_flow)
            response["Retry-After"] = "600"
            return response
        values = (uuid4().hex, camping, email, now_iso())
        if settings.CLOUD_ROLE and starter_flow:
            db.conn.execute("SELECT hpa_rating.submit_starter_request(?,?,?,?,?)", (*values,content))
        elif settings.CLOUD_ROLE:
            db.conn.execute("SELECT hpa_rating.submit_access_request(?,?,?,?)", values)
        else:
            inserted = db.conn.execute("""INSERT INTO access_requests(id,camping,email,created_at)
                                        VALUES(?,?,?,?) ON CONFLICT DO NOTHING""", values)
            if inserted.rowcount and starter_flow:
                if content:
                    db.conn.execute("INSERT INTO request_starters VALUES(?,?)", (values[0],content))
                count_starter(db, "request")
    return result
