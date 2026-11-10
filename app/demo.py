from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe

from .exporters import STATUS_LABELS
from .landing import public_response
from .referentiel import criteria_index, for_audit
from .scoring import applicable_criteria, compute_scores
from .storage import SAMPLE, sample_spec


# These are the only scenario choices a public URL can represent.
CHOICES = {"a-traiter": "TODO", "en-cours": "IN_PROGRESS", "valide": "VALIDATED"}
PROOFS = {"plan-reperage.pdf": "Plan de repérage", "releve-surfaces.pdf": "Relevé de surfaces",
          "fiche-location-velos.pdf": "Fiche de location de vélos"}


@require_safe
def demo(request):
    choice = request.GET.get("statut", "a-traiter")
    if choice not in CHOICES:
        raise Http404
    sample = sample_spec()
    audit = sample["audit"]
    stars = audit["target_stars"]
    ref = for_audit(audit)
    profile = {**audit["profile"], "type": audit["type"], "mention": audit["mention"]}
    by_id = criteria_index(ref)
    items = {item["criterion_id"]: item for item in sample["items"]}
    items["4"] = {"status": CHOICES[choice], "validated_stars": stars}
    rows = [r for r in applicable_criteria(ref, profile, stars, items) if r["code"] != "NA"]
    proofs = [{**proof, "title": PROOFS[proof["original_name"]]} for proof in sample["evidences"]]
    records = [{"number": item["criterion_id"], "title": by_id[item["criterion_id"]]["title"],
                "status": STATUS_LABELS[item["status"]], "notes": item["notes"]}
               for item in sorted(sample["items"], key=lambda i: int(i["criterion_id"]))]
    context = {"exercise": by_id["4"], "choice": choice, "proofs": proofs, "records": records,
               "stars": stars, "capacity": profile["nb_emplacements"], "total": len(rows),
               "filled": sum(row["status"] != "TODO" for row in rows),
               "score": compute_scores(ref, profile, stars, items)}
    return public_response(request, "demo.html", context)


@require_safe
def proof(request, name):
    if name not in PROOFS:
        raise Http404
    response = FileResponse((SAMPLE / name).open("rb"), content_type="application/pdf", filename=name)
    response["X-Robots-Tag"] = "noindex"
    return response
