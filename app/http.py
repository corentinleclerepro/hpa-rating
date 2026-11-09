import re
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from hpa_shared.http import error


class EvidenceBody:
    """Preserve the original MIME bytes before Django's CSRF form lookup reads the stream."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and re.fullmatch(r"/api/audits/[0-9a-f]+/items/[0-9]+/evidence", request.path):
            if not request.session.get("guest"):
                return error("Saisissez votre code personnel.", 401)
            if int(request.META.get("CONTENT_LENGTH") or 0) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                return error("Envoyez au maximum 64 Mo à la fois.", 413)
            try:
                request.evidence_mime = request.body
            except RequestDataTooBig:
                return error("Envoyez au maximum 64 Mo à la fois.", 413)
        return self.get_response(request)
