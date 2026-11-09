import json
from functools import wraps
from django.http import JsonResponse


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def payload(request):
    try:
        value = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Le formulaire est illisible.") from exc
    if not isinstance(value, dict):
        raise ValueError("Le formulaire est invalide.")
    return value


def endpoint(methods):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return error("Méthode non autorisée.", 405)
            try:
                return view(request, *args, **kwargs)
            except ValueError as exc:
                return error(str(exc))
            except FileNotFoundError:
                return error("Ressource introuvable.", 404)
        return wrapped
    return decorate


def csrf_failure(request, reason=""):
    return error("La session a changé. Rechargez la page et réessayez.", 403)


class PrivateHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Frame-Options"] = "DENY"
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "private, no-store"
        response["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        return response
