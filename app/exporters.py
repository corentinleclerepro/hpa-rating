import html
import json
import os
import re
import zipfile
from datetime import datetime

from . import scoring
from .referentiel import criteria_index

STATUS_LABELS = {
    "TODO": "À traiter",
    "IN_PROGRESS": "En cours",
    "EVIDENCE_MISSING": "Preuve manquante",
    "NON_COMPLIANT": "Non conforme (action requise)",
    "VALIDATED": "Validé (prêt pour audit)",
    "NA": "Non applicable",
}

CODE_LABELS = {"X": "Obligatoire", "ONC": "Obligatoire non compensable", "O": "À la carte",
               "PRQ": "Prérequis", "NA": "NA", "AJO": "AJO"}


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
    return s[:60] or "x"


def evidence_kind(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"):
        return "PHOTO"
    if ext == ".pdf":
        return "PDF"
    return "DOC"


def chapter_title(ref, chapter_id):
    for ch in ref.get("chapters", []):
        if ch["id"] == chapter_id:
            return ch["titre"]
    return f"Chapitre {chapter_id}"


def zip_path_for(ref, crit, filename):
    ch = f"Chapitre_{crit.get('chapter', 0)}_{slugify(chapter_title(ref, crit.get('chapter', 0)))}"
    section = f"{slugify(crit.get('section', 'General'))}"
    crit_dir = f"Critere_{crit['id']}_{slugify(crit.get('title', ''))}"
    return os.path.join(ch, section, crit_dir, filename)


def safe_filename(cid, seq, original):
    ext = os.path.splitext(original or "")[1].lower() or ""
    base = slugify(os.path.splitext(original or "fichier")[0])[:40]
    return f"C{cid}_{seq:02d}_{base}{ext}"


def build_book_html(audit, ref, items, evidences, score, link_base):
    idx = criteria_index(ref)
    profile = audit["profile"]
    stars = score["stars"]
    esc = html.escape

    def ev_link(ev):
        if ev["kind"] == "URL":
            return f'<a href="{esc(ev["url"])}" target="_blank">{esc(ev["url"])}</a>'
        name = ev["filename"]
        if link_base == "ZIP":
            crit = idx.get(ev["criterion_id"], {"id": ev["criterion_id"], "chapter": 0, "section": "", "title": ""})
            href = zip_path_for(ref, crit, name)
        else:
            href = f"{link_base}/api/audits/{audit['id']}/evidence/{ev['id']}/file"
        return f'<a href="{esc(href)}" target="_blank">{esc(ev["original_name"] or name)}</a>'

    rows = []
    by_crit = {}
    for ev in evidences:
        by_crit.setdefault(ev["criterion_id"], []).append(ev)

    appl = {a["id"]: a for a in scoring.applicable_criteria(ref, {**profile, "type": audit["type"], "mention": audit["mention"]}, stars)}
    ordered = sorted(ref.get("criteria", []), key=lambda c: (c.get("chapter", 0), int(c["id"]) if str(c["id"]).isdigit() else 9999, c["id"]))

    for c in ordered:
        a = appl.get(c["id"], {"code": "NA", "points": 0, "ajo": False})
        if a["code"] == "NA":
            continue
        it = items.get(c["id"], {})
        status = it.get("status", "TODO")
        evs = by_crit.get(c["id"], [])
        badges = f'<span class="badge code-{a["code"]}">{a["code"]}</span>'
        if a["ajo"]:
            badges += ' <span class="badge ajo">AJO</span>'
        ev_html = "".join(
            f'<li>[{esc(ev["kind"])}] {ev_link(ev)}'
            + (f' — <em>{esc(ev["caption"])}</em>' if ev["caption"] else "")
            + (' <span class="badge stale">à rafraîchir</span>' if ev["stale"] else "")
            + "</li>"
            for ev in evs
        )
        rows.append(f"""
        <div class="crit">
          <h3>Critère {esc(c['id'])} — {esc(c.get('title',''))} {badges} <span class="pts">{a['points']} pt</span></h3>
          <p class="status">Statut : <strong>{esc(STATUS_LABELS.get(status, status))}</strong>
             {(' — validé par ' + esc(it['validated_by']) + ' le ' + esc(it['validated_at'][:10])) if it.get('validated_by') else ''}</p>
          {('<p class="precisions">' + esc(c.get('precisions','')) + '</p>') if c.get('precisions') else ''}
          {('<p class="notes">' + esc(it.get('notes','')).replace(chr(10),'<br>') + '</p>') if it.get('notes') else ''}
          {('<ul class="evs">' + ev_html + '</ul>') if ev_html else '<p class="noev">Aucune preuve jointe</p>'}
        </div>""")

    x = score["x"]
    o = score["o"]
    blockers_html = "".join(
        f'<li><strong>{esc(b["type"])}</strong> : {esc(", ".join(b["criteria"]))} — {esc(b["message"])}</li>'
        for b in score["blockers"]
    ) or "<li>Aucun blocage</li>"

    verdict = "ÉLIGIBLE" if score["eligible"] else "NON ÉLIGIBLE"
    verdict_class = "ok" if score["eligible"] else "ko"

    prof_rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(str(v))}</td></tr>" for k, v in profile.items())

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Book de synthèse — {esc(audit['name'])}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 40px; color: #222; }}
h1 {{ color: #0b5394; }} h2 {{ color: #0b5394; border-bottom: 2px solid #0b5394; padding-bottom: 4px; }}
.verdict {{ font-size: 24px; font-weight: bold; padding: 10px; border-radius: 6px; }}
.verdict.ok {{ background: #d4edda; color: #155724; }}
.verdict.ko {{ background: #f8d7da; color: #721c24; }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 6px 10px; }}
.crit {{ border: 1px solid #ddd; border-radius: 6px; padding: 10px 14px; margin: 10px 0; page-break-inside: avoid; }}
.badge {{ background: #eee; border-radius: 4px; padding: 1px 6px; font-size: 12px; }}
.badge.X {{ background: #f8d7da; }} .badge.ONC {{ background: #ffc107; }} .badge.O {{ background: #d1ecf1; }}
.badge.PRQ {{ background: #721c24; color: #fff; }} .badge.ajo {{ background: #6f42c1; color: #fff; }}
.badge.stale {{ background: #ffeeba; }}
.pts {{ color: #666; font-size: 13px; }} .precisions {{ color: #555; font-size: 13px; }}
.noev {{ color: #a00; font-size: 13px; }} ul.evs {{ margin: 4px 0; }}
.scores td {{ font-size: 15px; }}
@media print {{ body {{ margin: 10mm; }} }}
</style></head><body>
<h1>Book de synthèse — Pré-audit de classement</h1>
<p><em>Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — outil de préparation, ne remplace pas la visite de l'organisme évaluateur accrédité COFRAC.</em></p>
<h2>Fiche d'identité</h2>
<table>
<tr><td>Établissement</td><td>{esc(audit['name'])}</td></tr>
<tr><td>Type</td><td>{esc(audit['type'])}</td></tr>
<tr><td>Mention</td><td>{esc(audit['mention'])}</td></tr>
<tr><td>Catégorie visée</td><td>{stars} ★</td></tr>
{prof_rows}
</table>
<h2>Résultat du calcul ({stars} ★ visée)</h2>
<p class="verdict {verdict_class}">{verdict}</p>
<table class="scores">
<tr><th>Points obligatoires (X)</th><td>{x['obtained']} / {x['total']} atteints ({int(x['ratio']*100)} %, seuil 95 %, marge {x['margin_points']} pt)</td></tr>
<tr><th>Points à la carte (O)</th><td>{o['obtained']} / {o['total']} — requis : {o['required']} (seuil {int(o['threshold_pct']*100)} % = {o['base_required']} pt{', + compensation ' + str(o['compensation']) + ' pt' if o['compensation'] else ''})</td></tr>
</table>
<h3>Blocages</h3><ul>{blockers_html}</ul>
<h2>Détail critère par critère</h2>
{''.join(rows)}
</body></html>"""


def build_manifest(audit, ref, items, evidences, score):
    idx = criteria_index(ref)
    stars = score["stars"]
    profile = {**audit["profile"], "type": audit["type"], "mention": audit["mention"]}
    appl = {a["id"]: a for a in scoring.applicable_criteria(ref, profile, stars)}
    crits = []
    for cid, it in items.items():
        c = idx.get(cid, {})
        a = appl.get(cid, {"code": "NA", "points": 0, "ajo": False})
        crits.append({
            "id": cid,
            "title": c.get("title", ""),
            "code": a["code"],
            "points": a["points"],
            "ajo": a["ajo"],
            "status": it.get("status", "TODO"),
            "notes": it.get("notes", ""),
            "validated_by": it.get("validated_by", ""),
            "evidences": [
                {"id": e["id"], "kind": e["kind"], "filename": e["filename"],
                 "original_name": e["original_name"], "url": e["url"], "caption": e["caption"], "stale": bool(e["stale"])}
                for e in evidences if e["criterion_id"] == cid
            ],
        })
    return {
        "etablissement": audit["name"],
        "type": audit["type"],
        "mention": audit["mention"],
        "categorie_visee": stars,
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "resultat": score,
        "criteres": crits,
        "source_referentiel": ref.get("meta", {}).get("source_url"),
    }


def build_zip(audit, ref, items, evidences, score, data_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    slug = slugify(audit["name"])
    date = datetime.now().strftime("%Y%m%d")
    root = f"Dossier_{slug}_{date}"
    zip_name = f"{root}.zip"
    zip_path = os.path.join(out_dir, zip_name)

    book = build_book_html(audit, ref, items, evidences, score, link_base="ZIP")
    manifest = build_manifest(audit, ref, items, evidences, score)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{root}/00_Book_de_synthese.html", book)
        z.writestr(f"{root}/00_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for ev in evidences:
            if ev["kind"] == "URL" or not ev["filename"]:
                continue
            crit = criteria_index(ref).get(ev["criterion_id"], {"id": ev["criterion_id"], "chapter": 0, "section": "", "title": ""})
            src = os.path.join(data_dir, "dossiers", audit["id"], "evidences", ev["criterion_id"], ev["filename"])
            if os.path.exists(src):
                z.write(src, os.path.join(root, zip_path_for(ref, crit, ev["filename"])))
    return zip_path
