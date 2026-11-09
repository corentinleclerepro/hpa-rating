from math import ceil

STAR_CARTE_THRESHOLDS = {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.30, 5: 0.40}
OBLIGATORY_RATIO = 0.95
COMPENSATION_FACTOR = 3
VALIDATED = "VALIDATED"
PENDING_STATUSES = ("TODO", "IN_PROGRESS", "EVIDENCE_MISSING")


def rule_for(criterion, stars, profile):
    rules = criterion.get("rules") or {}
    r = rules.get(str(stars))
    if r is None:
        r = rules.get("*")
    if r is None:
        return {"code": "NA", "points": 0}
    code = r.get("code", "NA")
    if code == "NA":
        return {"code": "NA", "points": 0}
    ptype = profile.get("type")
    if criterion.get("na_prl") and ptype == "prl":
        return {"code": "NA", "points": 0}
    if criterion.get("na_camping") and ptype == "camping":
        return {"code": "NA", "points": 0}
    applies_to = criterion.get("applies_to")
    if applies_to and ptype not in applies_to:
        return {"code": "NA", "points": 0}
    for key, val in (criterion.get("conditions") or {}).items():
        if profile.get(key) != val:
            return {"code": "NA", "points": 0}
    if code == "X" and profile.get("mention") == "loisirs" and criterion.get("loisirs_becomes") == "O":
        code = "O"
    return {"code": code, "points": int(r.get("points", 0))}


def is_ajo(criterion, profile):
    if criterion.get("ajo"):
        return True
    return bool(criterion.get("ajo_prl") and profile.get("type") == "prl")


def applicable_criteria(referentiel, profile, stars):
    out = []
    for c in referentiel.get("criteria", []):
        r = rule_for(c, stars, profile)
        out.append({
            "id": c["id"],
            "code": r["code"],
            "points": r["points"],
            "ajo": is_ajo(c, profile),
        })
    return out


def compute_scores(referentiel, profile, stars, statuses):
    appl = applicable_criteria(referentiel, profile, stars)

    def status_of(cid):
        return (statuses.get(cid) or {}).get("status", "TODO")

    prq = [a for a in appl if a["code"] == "PRQ"]
    onc = [a for a in appl if a["code"] == "ONC"]
    x = [a for a in appl if a["code"] == "X"]
    o = [a for a in appl if a["code"] == "O"]

    prq_missing = [a["id"] for a in prq if status_of(a["id"]) != VALIDATED]
    onc_missing = [a["id"] for a in onc if status_of(a["id"]) != VALIDATED]

    x_total = sum(a["points"] for a in x)
    x_obtained = sum(a["points"] for a in x if status_of(a["id"]) == VALIDATED)
    x_pending = sum(a["points"] for a in x if status_of(a["id"]) in PENDING_STATUSES)
    x_lost = x_total - x_obtained - x_pending
    not_attained = x_total - x_obtained
    margin = (1.0 - OBLIGATORY_RATIO) * x_total
    within_margin = not_attained <= margin + 1e-9

    o_total = sum(a["points"] for a in o)
    o_obtained = sum(a["points"] for a in o if status_of(a["id"]) == VALIDATED)
    threshold = STAR_CARTE_THRESHOLDS.get(stars, 0.40)
    base_required_o = ceil(threshold * o_total) if o_total else 0
    compensation = COMPENSATION_FACTOR * not_attained if within_margin else None
    required_o = base_required_o + compensation if within_margin else None

    ratio = (x_obtained / x_total) if x_total else 1.0

    blockers = []
    if prq_missing:
        blockers.append({"type": "PRQ", "criteria": prq_missing,
                         "message": "Prérequis non satisfaits (bloquants, non compensables)"})
    if onc_missing:
        blockers.append({"type": "ONC", "criteria": onc_missing,
                         "message": "Critères obligatoires non compensables non atteints"})

    eligible = (not blockers) and within_margin and (required_o is not None) and o_obtained >= required_o

    return {
        "stars": stars,
        "x": {
            "total": x_total, "obtained": x_obtained, "pending": x_pending, "lost": x_lost,
            "ratio": round(ratio, 4), "margin_points": round(margin, 2), "within_margin": within_margin,
            "threshold_pct": OBLIGATORY_RATIO,
        },
        "o": {
            "total": o_total, "obtained": o_obtained, "threshold_pct": threshold,
            "base_required": base_required_o, "compensation": compensation,
            "required": required_o, "ok": bool(within_margin and o_obtained >= required_o),
        },
        "blockers": blockers,
        "eligible": bool(eligible),
    }


def reachable_stars(referentiel, profile, statuses):
    return {s: compute_scores(referentiel, profile, s, statuses)["eligible"] for s in range(1, 6)}
