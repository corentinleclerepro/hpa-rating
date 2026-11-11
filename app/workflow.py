"""Ordered preparation, independent of whether the dossier would qualify for a star rating."""
from .referentiel import for_audit
from .scoring import applicable_criteria

STEPS = ("profile", "prerequisites", "criteria", "proofs", "summary")
LABELS = ("Profil", "Prérequis", "Critères", "Justificatifs", "Synthèse et export")


def profile_ready(profile):
    total = profile.get("nb_emplacements")
    return type(total) is int and total > 0


def ordered_groups(ref, rows):
    chapters = {c["id"]: c.get("chapter") for c in ref["criteria"]}
    active = sorted((r for r in rows if r["code"] != "NA"), key=lambda r: int(r["id"]))
    return {key: [r for r in active if (chapters[r["id"]] == 0) == (key == "prerequisites")]
            for key in ("prerequisites", "criteria")}


def progress(audit, items, rows=None):
    ref = for_audit(audit)
    if rows is None:
        profile = {**audit["profile"], "type": audit["type"], "mention": audit["mention"]}
        rows = applicable_criteria(ref, profile, audit["target_stars"], items)
    groups = ordered_groups(ref, rows)
    confirmed = bool(audit.get("profile_confirmed")) and profile_ready(audit["profile"])
    current = "profile" if not confirmed else None
    allowed, counts = [], {}
    next_id = None
    for key, group in groups.items():
        counts[key] = {"total": len(group), "filled": sum(r["status"] != "TODO" for r in group)}
        if current is not None:
            continue
        for row in group:
            allowed.append(row["id"])
            if row["status"] == "TODO":
                current, next_id = key, row["id"]
                break
    if current is None:
        current = "summary" if audit.get("proofs_reviewed") else "proofs"
    index = STEPS.index(current)
    return {"current": current, "number": index + 1, "next_id": next_id, "open_steps": list(STEPS[:index + 1]),
            "allowed_ids": allowed, "counts": counts}


def explain(flow):
    if flow["next_id"]:
        return f"Renseignez d’abord le critère {flow['next_id']} pour poursuivre le parcours."
    if flow["current"] == "profile":
        return "Confirmez d’abord le profil de l’établissement pour ouvrir les prérequis."
    return "Vérifiez d’abord les justificatifs et confirmez leur revue pour ouvrir la synthèse."
