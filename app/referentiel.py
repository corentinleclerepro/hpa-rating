import json
import os
from datetime import date

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "referentiel.json")
LEGACY_PATH = os.path.join(os.path.dirname(DEFAULT_PATH), "referentiel-v1.json")
LEGACY_VERSION = "extrait-v1"
CURRENT_VERSION = "atout-france-2019-195"

_cache = {}


def load(path=None):
    path = path or os.environ.get("REFERENTIEL_PATH", DEFAULT_PATH)
    mtime = os.path.getmtime(path)
    if path in _cache and _cache[path][0] == mtime:
        return _cache[path][1]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[path] = (mtime, data)
    return data


def criteria_index(ref):
    return {c["id"]: c for c in ref.get("criteria", [])}


def for_audit(audit):
    return load(LEGACY_PATH) if audit.get("reference_version") == LEGACY_VERSION else load()


def publication(ref):
    meta = ref["meta"]
    count = len(ref["criteria"])
    if not meta.get("version"):
        return {"label": f"Ancien extrait du référentiel · {count} critères", "version": LEGACY_VERSION}
    def french_date(value):
        months = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()
        day = date.fromisoformat(value)
        return f"{'1er' if day.day == 1 else day.day} {months[day.month - 1]} {day.year}"
    effective = meta.get("applicable_depuis")
    checked = meta.get("source_verifiee_le")
    label = f"Référentiel Camping et PRL · {count} critères"
    return {"label": label + (f" · applicable depuis le {french_date(effective)}" if effective else ""),
            "version": meta["version"], "checked": french_date(checked) if checked else "",
            "source": meta.get("source_url"), "annexe": meta.get("annexe_url")}


def stats(ref):
    crits = ref.get("criteria", [])
    return {
        "nb_criteria": len(crits),
        "nb_validated": sum(1 for c in crits if c.get("validated")),
        "nb_ajo": sum(1 for c in crits if c.get("ajo") or c.get("ajo_prl")),
        "chapters": ref.get("chapters", []),
        "source_url": ref.get("meta", {}).get("source_url"),
        "validated": ref.get("meta", {}).get("validated", False),
    }
