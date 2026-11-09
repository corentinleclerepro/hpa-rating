import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "referentiel.json")

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
