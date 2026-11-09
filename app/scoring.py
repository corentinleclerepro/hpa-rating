from math import ceil

STAR_CARTE_THRESHOLDS = {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.30, 5: 0.40}
OBLIGATORY_RATIO = 0.95
COMPENSATION_FACTOR = 3
VALIDATED = "VALIDATED"
PENDING_STATUSES = ("TODO", "IN_PROGRESS", "EVIDENCE_MISSING")
GROUP_FIELDS = {
    "caravanes": "nb_emplacements_caravanes", "hll_rml": "nb_emplacements_hll_rml",
    "prl_locatifs": "nb_emplacements_locatifs", "aire_autocaravane": "has_aire_autocaravane",
    "non_raccordes": "has_non_raccordes", "raccordes": "has_raccordes",
    "confort": "has_confort", "grand_confort": "has_grand_confort",
    "confort_sans_wc": "has_confort_sans_wc",
}


def group_absent(group, profile):
    if group == "locatifs":
        count = profile.get("nb_emplacements_locatifs")
        flag = profile.get("has_locatifs")
        return (count == 0 or flag is False) and not (count or flag)
    value = profile.get(GROUP_FIELDS.get(group))
    return value is not None and value == 0


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
    if (group_absent(criterion.get("profile_group"), profile)
            or (criterion.get("wifi_exemption") and
                (profile.get("wifi_sans_positionnement") or profile.get("wifi_impossible")))
            or (criterion.get("pool_exemption") and profile.get("has_pool") is False)
            or (criterion.get("reception_exemption") and ptype == "prl" and stars <= 2
                and profile.get("has_reception") is False)):
        return {"code": "NA", "points": 0}
    threshold = criterion.get("optional_below_pitches")
    count = profile.get("nb_emplacements")
    if threshold and isinstance(count, int) and 0 < count < threshold and code == "X":
        code = "O"
    flag = criterion.get("optional_profile")
    if code == "X" and profile.get(flag) and (flag != "camping_outremer" or ptype == "camping"):
        code = "O"
    if code == "X" and profile.get("mention") == "loisirs" and criterion.get("loisirs_becomes") == "O":
        code = "O"
    return {"code": code, "points": int(r.get("points", 0))}


def is_ajo(criterion, profile):
    if criterion.get("ajo"):
        return True
    return bool(criterion.get("ajo_prl") and profile.get("type") == "prl")


def applicable_criteria(referentiel, profile, stars, items=None):
    if stars not in STAR_CARTE_THRESHOLDS:
        raise ValueError("La catégorie doit être comprise entre 1 et 5 étoiles")
    items = items or {}
    out = {}
    criteria = referentiel.get("criteria", [])
    by_id = {c["id"]: c for c in criteria}
    for c in criteria:
        r = rule_for(c, stars, profile)
        item = items.get(c["id"], {})
        status = item.get("status", "TODO")
        checked = item.get("validated_stars")
        basis = by_id[c.get("bonus_basis", c["id"])]["rules"]
        if status == VALIDATED and checked and stars > checked:
            if basis.get(str(stars), {}).get("exigence") != basis.get(str(checked), {}).get("exigence"):
                status = "TODO"
        out[c["id"]] = {
            "id": c["id"],
            "code": r["code"],
            "points": r["points"],
            "ajo": is_ajo(c, profile),
            "status": status,
            "earned": (item.get("awarded_points") or 0) if c.get("points_min") else r["points"],
        }
    # Reverse order propagates chains such as 61 → 60 → 59 within this simulation.
    for c in reversed(criteria):
        if stars <= c.get("validates_previous_through", 0):
            current = out[c["id"]]
            previous = out[str(int(c["id"]) - 1)]
            if current["code"] != "NA" and current["status"] == VALIDATED and previous["code"] != "NA":
                if previous["status"] != VALIDATED:
                    previous.update(status=VALIDATED, via=c["id"])
    if stars == 1:
        for c in criteria:
            required = c.get("optional_when_validated")
            if required and out[c["id"]]["code"] == "X" and all(
                    out[cid]["code"] != "NA" and out[cid]["status"] == VALIDATED for cid in required):
                out[c["id"]]["code"] = "O"
    return list(out.values())


def compute_scores(referentiel, profile, stars, statuses):
    appl = applicable_criteria(referentiel, profile, stars, statuses)

    prq = [a for a in appl if a["code"] == "PRQ"]
    onc = [a for a in appl if a["code"] == "ONC"]
    mandatory_codes = ("X", "ONC") if referentiel.get("meta", {}).get("version") else ("X",)
    x = [a for a in appl if a["code"] in mandatory_codes]
    o = [a for a in appl if a["code"] == "O"]

    prq_missing = [a["id"] for a in prq if a["status"] != VALIDATED]
    onc_missing = [a["id"] for a in onc if a["status"] != VALIDATED]

    x_total = sum(a["points"] for a in x)
    x_obtained = sum(a["points"] for a in x if a["status"] == VALIDATED)
    x_pending = sum(a["points"] for a in x if a["status"] in PENDING_STATUSES)
    x_lost = x_total - x_obtained - x_pending
    not_attained = x_total - x_obtained
    margin = (1.0 - OBLIGATORY_RATIO) * x_total
    within_margin = not_attained <= margin + 1e-9

    o_total = sum(a["points"] for a in o)
    o_obtained = sum(a["earned"] for a in o if a["status"] == VALIDATED)
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
