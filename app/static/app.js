const app = document.getElementById("app");
let META = null;
let REF = null;
let currentAuditId = null;
let viewStars = null;
let criteriaCache = null;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const ct = res.headers.get("Content-Type") || "";
  if (!res.ok) {
    let msg = res.statusText;
    if (ct.includes("json")) {
      const j = await res.json();
      msg = j.error || msg;
    }
    throw new Error(msg);
  }
  if (ct.includes("json")) return res.json();
  return res;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function flash(msg) {
  const d = document.createElement("div");
  d.className = "flash";
  d.textContent = msg;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 3500);
}

function route() {
  const h = location.hash || "#/";
  if (h.startsWith("#/dossier/")) return renderDossier(h.split("/")[2]);
  if (h.startsWith("#/referentiel")) return renderReferentiel();
  return renderList();
}

async function boot() {
  META = await api("/api/meta");
  REF = await api("/api/referentiel");
  route();
}

async function renderList() {
  const { audits } = await api("/api/audits");
  let html = `<h2>Vos dossiers de classement</h2>`;
  if (!audits.length) html += `<p class="muted">Aucun dossier. Créez-en un ci-dessous.</p>`;
  for (const a of audits) {
    const pct = a.nb_items ? Math.round((a.nb_validated / a.nb_items) * 100) : 0;
    html += `<div class="card"><div class="row" style="justify-content:space-between">
      <div>
        <strong style="font-size:16px">${esc(a.name)}</strong><br>
        <span class="muted">${esc(a.type)} — mention ${esc(a.mention)} — vise ${a.target_stars}★ — ${a.nb_validated}/${a.nb_items} critères validés (${pct} %) — ${a.nb_evidences} preuves</span>
      </div>
      <div class="row">
        <a class="btn" href="#/dossier/${a.id}">Ouvrir</a>
        <button class="secondary" onclick="cloneAudit('${a.id}','${esc(a.name).replace(/'/g, "\\'")}')">Cloner (renouvellement)</button>
        <button class="danger" onclick="deleteAudit('${a.id}')">Supprimer</button>
      </div></div></div>`;
  }
  html += `<h2>Nouveau dossier</h2><div class="card"><div class="form-grid">
    <div><label>Nom de l'établissement</label><input id="f_name" placeholder="Camping Les Example"></div>
    <div><label>Type</label><select id="f_type"><option value="camping">Camping / caravanage</option><option value="prl">PRL (régime hôtelier)</option></select></div>
    <div><label>Mention</label><select id="f_mention"><option value="tourisme">Tourisme</option><option value="loisirs">Loisirs</option></select></div>
    <div><label>Catégorie visée</label><select id="f_stars">${[1,2,3,4,5].map(s => `<option value="${s}" ${s === 3 ? "selected" : ""}>${s}★</option>`).join("")}</select></div>`;
  for (const f of META.profile_fields) {
    if (f.type === "bool") html += `<div><label>${esc(f.label)}</label><select id="pf_${f.key}"><option value="false">Non</option><option value="true">Oui</option></select></div>`;
    else html += `<div><label>${esc(f.label)}</label><input id="pf_${f.key}" type="number" value="0"></div>`;
  }
  html += `</div><br><button onclick="createAudit()">Créer le dossier</button></div>`;
  app.innerHTML = html;
}

window.createAudit = async function () {
  const profile = {};
  for (const f of META.profile_fields) {
    const el = document.getElementById("pf_" + f.key);
    profile[f.key] = f.type === "bool" ? el.value === "true" : (parseInt(el.value) || 0);
  }
  try {
    const { audit } = await api("/api/audits", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: document.getElementById("f_name").value, type: document.getElementById("f_type").value, mention: document.getElementById("f_mention").value, target_stars: +document.getElementById("f_stars").value, profile }),
    });
    location.hash = "#/dossier/" + audit.id;
  } catch (e) { flash(e.message); }
};

window.cloneAudit = async function (id, name) {
  try {
    const { audit } = await api(`/api/audits/${id}/clone`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name + " — renouvellement" }) });
    flash("Dossier cloné (preuves marquées « à rafraîchir »)");
    renderList();
  } catch (e) { flash(e.message); }
};

window.deleteAudit = async function (id) {
  if (!confirm("Supprimer ce dossier et toutes ses preuves ?")) return;
  try { await api(`/api/audits/${id}`, { method: "DELETE" }); renderList(); } catch (e) { flash(e.message); }
};

async function renderDossier(id) {
  currentAuditId = id;
  const data = await api(`/api/audits/${id}`);
  const stars = viewStars || data.audit.target_stars;
  const crit = await api(`/api/audits/${id}/criteria?stars=${stars}`);
  criteriaCache = crit;
  const sc = await api(`/api/audits/${id}/score?stars=${stars}`);
  drawDossier(data, crit, sc, stars);
}

function drawDossier(data, crit, sc, stars) {
  const a = data.audit;
  const s = sc.score;
  const xPct = s.x.total ? Math.round((s.x.obtained / s.x.total) * 100) : 100;
  const oReq = s.o.required ?? 0;
  const oPct = s.o.total ? Math.min(100, Math.round((s.o.obtained / Math.max(1, s.o.required || 1)) * 100)) : 100;
  const xClass = s.x.within_margin ? (xPct >= 95 ? "" : "bad") : "bad";
  const oClass = s.o.ok ? "" : "bad";

  let html = `<div class="topbar">
    <a class="btn secondary" href="#/">← Dossiers</a>
    <input id="d_name" value="${esc(a.name)}" style="font-weight:700">
    <select id="d_type"><option value="camping" ${a.type === "camping" ? "selected" : ""}>Camping</option><option value="prl" ${a.type === "prl" ? "selected" : ""}>PRL</option></select>
    <select id="d_mention"><option value="tourisme" ${a.mention === "tourisme" ? "selected" : ""}>Tourisme</option><option value="loisirs" ${a.mention === "loisirs" ? "selected" : ""}>Loisirs</option></select>
    <label>Catégorie visée <select id="d_stars">${[1,2,3,4,5].map(x => `<option value="${x}" ${x === a.target_stars ? "selected" : ""}>${x}★</option>`).join("")}</select></label>
    <button onclick="saveAudit()">Enregistrer</button>
    <span style="flex:1"></span>
    <a class="btn" href="/api/audits/${a.id}/export/zip?stars=${stars}">⬇ Export ZIP (dossier preuves)</a>
    <a class="btn secondary" target="_blank" href="/api/audits/${a.id}/export/book?stars=${stars}">📖 Book de synthèse (PDF via imprimer)</a>
  </div>`;

  html += `<div class="card">
    <div class="row" style="justify-content:space-between">
      <div><strong>Simulation « what-if » :</strong> voir le dossier en
        <span class="star-btns">${[1,2,3,4,5].map(x => `<button class="${x === stars ? "active" : "secondary"}" onclick="setStars(${x})">${x}★</button>`).join("")}</span>
      </div>
      <span class="verdict ${s.eligible ? "ok" : "ko"}">${s.eligible ? "✓ ÉLIGIBLE" : "✗ NON ÉLIGIBLE"} en ${stars}★</span>
    </div>
    <p class="muted">Étoiles atteignables actuellement : ${[1,2,3,4,5].filter(x => sc.reachable[x]).map(x => x + "★").join(", ") || "aucune"}</p>
    <div class="gauge-label">Points obligatoires (X) : <strong>${s.x.obtained}/${s.x.total}</strong> = ${xPct} % (seuil 95 % — marge autorisée ${s.x.margin_points} pt ; en attente ${s.x.pending} pt, non conformes ${s.x.lost} pt)</div>
    <div class="gauge"><div class="fill ${xClass}" style="width:${xPct}%"></div><div class="marker" style="left:95%"></div></div>
    <div class="gauge-label">Points à la carte (O) : <strong>${s.o.obtained}</strong> obtenus — requis <strong>${oReq}</strong> (seuil ${Math.round(s.o.threshold_pct * 100)} % = ${s.o.base_required} pt${s.o.compensation ? ` + compensation ${s.o.compensation} pt (3 × points X perdus)` : ""})</div>
    <div class="gauge"><div class="fill ${oClass}" style="width:${Math.min(100, oPct)}%"></div></div>
    ${s.blockers.length ? `<div class="blockers"><strong>🚫 Blocages :</strong><ul>${s.blockers.map(b => `<li><span class="badge ${b.type}">${b.type}</span> critères ${esc(b.criteria.join(", "))} — ${esc(b.message)}</li>`).join("")}</ul></div>` : `<p class="muted">Aucun blocage (prérequis OK, aucun ONC non atteint).</p>`}
    <p class="muted">Profil : ${Object.entries(a.profile).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(", ") || "non renseigné"}</p>
  </div>`;

  html += `<div class="filters">
    <input id="f_search" placeholder="Rechercher un critère…" oninput="drawCriteria()">
    <select id="f_status" onchange="drawCriteria()">
      <option value="">Tous statuts</option>
      ${META.statuses.map(st => `<option value="${st}">${META.status_labels[st]}</option>`).join("")}
    </select>
    <label><input type="checkbox" id="f_ajo" onchange="drawCriteria()"> AJO uniquement (à justifier à l'inspection)</label>
    <label><input type="checkbox" id="f_missing" onchange="drawCriteria()"> preuves manquantes</label>
  </div>`;

  html += `<div id="crit_list"></div>`;
  app.innerHTML = html;
  drawCriteria();
}

window.setStars = function (x) { viewStars = x; renderDossier(currentAuditId); };

window.saveAudit = async function () {
  try {
    await api(`/api/audits/${currentAuditId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: document.getElementById("d_name").value, type: document.getElementById("d_type").value, mention: document.getElementById("d_mention").value, target_stars: +document.getElementById("d_stars").value }),
    });
    flash("Dossier enregistré");
    viewStars = null;
    renderDossier(currentAuditId);
  } catch (e) { flash(e.message); }
};

function drawCriteria() {
  const crit = criteriaCache;
  const q = (document.getElementById("f_search").value || "").toLowerCase();
  const st = document.getElementById("f_status").value;
  const ajoOnly = document.getElementById("f_ajo").checked;
  const missOnly = document.getElementById("f_missing").checked;
  let html = "";
  let lastChapter = null, lastSection = null;
  for (const c of crit.criteria) {
    if (c.code === "NA") continue;
    if (q && !(c.title + " " + c.id + " " + c.section).toLowerCase().includes(q)) continue;
    if (st && c.status !== st) continue;
    if (ajoOnly && !c.ajo) continue;
    if (missOnly && c.nb_evidences > 0 && c.status !== "EVIDENCE_MISSING") continue;
    if (c.chapter !== lastChapter) { html += `<div class="chapter-title">${esc(crit.chapters.find(ch => ch.id === c.chapter)?.titre || ("Chapitre " + c.chapter))}</div>`; lastChapter = c.chapter; lastSection = null; }
    if (c.section !== lastSection) { html += `<div class="section-title">${esc(c.section)}</div>`; lastSection = c.section; }
    html += critCard(c);
  }
  document.getElementById("crit_list").innerHTML = html || `<p class="muted">Aucun critère ne correspond aux filtres.</p>`;
  for (const id of openCrits) refreshEvidences(id);
}

function critCard(c) {
  const open = openCrits.has(c.id) ? "open" : "";
  return `<div class="crit" id="crit_${c.id}">
    <div class="head" onclick="toggleCrit('${c.id}')">
      <span class="crit-id">${esc(c.id)}</span>
      <span class="badge ${c.code}">${c.code}</span>
      ${c.ajo ? '<span class="badge AJO">AJO</span>' : ""}
      <span class="title">${esc(c.title)} <span class="muted">(${c.points} pt)</span></span>
      <span class="badge st-${c.status}">${esc(META.status_labels[c.status] || c.status)}</span>
      ${c.nb_evidences ? `<span class="muted">📎 ${c.nb_evidences}</span>` : '<span class="muted">📎 0</span>'}
    </div>
    ${open ? `<div class="body">${critBody(c)}</div>` : ""}
  </div>`;
}

const openCrits = new Set();
window.toggleCrit = function (id) {
  if (openCrits.has(id)) openCrits.delete(id); else openCrits.add(id);
  const el = document.getElementById("crit_" + id);
  if (el) el.outerHTML = critCard(criteriaCache.criteria.find(c => c.id === id));
  if (openCrits.has(id)) refreshEvidences(id);
};

function critBody(c) {
  return `<p class="muted">${esc(c.precisions || "")}</p>
  <div class="row">
    <div><label>Statut</label><select id="st_${c.id}">${META.statuses.map(st => `<option value="${st}" ${st === c.status ? "selected" : ""}>${META.status_labels[st]}</option>`).join("")}</select></div>
    <div><label>Validé par</label><input id="vb_${c.id}" value="${esc(c.validated_by || "")}" placeholder="Nom"></div>
    <button onclick="saveItem('${c.id}')">Enregistrer le statut</button>
  </div>
  <div><label>Notes internes / commentaires pour l'auditeur</label><textarea id="nt_${c.id}">${esc(c.notes || "")}</textarea></div>
  <div class="row" style="margin-top:8px">
    <label>Ajouter des preuves (photos, PDF…) <input type="file" id="up_${c.id}" multiple></label>
    <button onclick="upload('${c.id}')">⬆ Envoyer</button>
  </div>
  <div class="row">
    <input id="url_${c.id}" placeholder="https://… (preuve numérique : site web, capture…)" style="flex:1">
    <button class="secondary" onclick="addUrl('${c.id}')">+ Lien URL</button>
  </div>
  <div id="ev_${c.id}"></div>`;
}

async function refreshEvidences(cid) {
  const data = await api(`/api/audits/${currentAuditId}`);
  const evs = data.evidences.filter(e => e.criterion_id === cid);
  const box = document.getElementById("ev_" + cid);
  if (!box) return;
  box.innerHTML = evs.map(e => {
    const label = e.kind === "URL" ? e.url : (e.original_name || e.filename);
    return `<span class="ev-chip">[${e.kind}] <a target="_blank" href="/api/audits/${currentAuditId}/evidence/${e.id}/file">${esc(label)}</a>
      ${e.stale ? '<span class="badge stale">à rafraîchir</span>' : ""}
      <input value="${esc(e.caption || "")}" placeholder="légende…" onchange="capEv('${e.id}', this.value)" style="width:140px">
      <button class="secondary" onclick="staleEv('${e.id}', ${e.stale ? 0 : 1})">${e.stale ? "Marquer OK" : "À rafraîchir"}</button>
      <button class="danger" onclick="delEv('${e.id}')">✕</button></span>`;
  }).join("") || '<p class="muted">Aucune preuve pour ce critère.</p>';
}

window.saveItem = async function (cid) {
  try {
    const item = await api(`/api/audits/${currentAuditId}/items/${cid}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: document.getElementById("st_" + cid).value, notes: document.getElementById("nt_" + cid).value, validated_by: document.getElementById("vb_" + cid).value }),
    });
    flash("Critère " + cid + " enregistré");
    renderDossier(currentAuditId);
  } catch (e) { flash(e.message); }
};

window.upload = async function (cid) {
  const input = document.getElementById("up_" + cid);
  if (!input.files.length) return flash("Choisissez au moins un fichier");
  const fd = new FormData();
  const caps = {};
  for (const f of input.files) { fd.append("files", f, f.name); caps[f.name] = ""; }
  fd.append("captions", new Blob([JSON.stringify(caps)], { type: "application/json" }));
  try {
    await api(`/api/audits/${currentAuditId}/items/${cid}/evidence`, { method: "POST", body: fd });
    flash("Preuve(s) envoyée(s)");
    renderDossier(currentAuditId);
  } catch (e) { flash(e.message); }
};

window.addUrl = async function (cid) {
  const url = document.getElementById("url_" + cid).value.trim();
  if (!url) return;
  try { await api(`/api/audits/${currentAuditId}/items/${cid}/evidence/url`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }); renderDossier(currentAuditId); }
  catch (e) { flash(e.message); }
};

window.delEv = async function (eid) {
  if (!confirm("Supprimer cette preuve ?")) return;
  try { await api(`/api/evidence/${eid}`, { method: "DELETE" }); renderDossier(currentAuditId); } catch (e) { flash(e.message); }
};

window.capEv = async function (eid, caption) {
  try { await api(`/api/evidence/${eid}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ caption }) }); } catch (e) { flash(e.message); }
};

window.staleEv = async function (eid, stale) {
  try { await api(`/api/evidence/${eid}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stale }) }); renderDossier(currentAuditId); } catch (e) { flash(e.message); }
};

async function renderReferentiel() {
  const st = await api("/api/referentiel/stats");
  const ref = REF;
  let html = `<div class="card"><h2>Référentiel Atout France</h2>
    <p><strong>${st.nb_criteria}</strong> critères chargés — <strong>${st.nb_validated}</strong> validés humainement — <strong>${st.nb_ajo}</strong> critères AJO (à justifier à l'inspection).</p>
    <p class="muted">Source : <a href="${esc(st.source_url)}" target="_blank">tableau de classement officiel (arrêté du 10 avril 2019)</a>.
    Règles de calcul : ≥ 95 % des points obligatoires (X) ; chaque point X perdu (dans la marge de 5 %) compensé par 3 points à la carte (O) ; seuils O par catégorie : 5/10/20/30/40 % pour 1★–5★ ; PRQ et ONC non compensables.</p>
    ${st.validated ? "" : `<p class="blockers"><strong>⚠ Référentiel non encore validé</strong> : complétez/validez <code>data/referentiel.json</code> depuis le PDF officiel avant usage en production (champ <code>"validated": true</code> par critère).</p>`}
  </div><div class="card"><table><tr><th>ID</th><th>Chapitre</th><th>Section</th><th>Critère</th><th>Statuts 1★→5★</th><th>Validé</th></tr>`;
  for (const c of ref.criteria) {
    const codes = [1,2,3,4,5].map(s => (c.rules[String(s)] || c.rules["*"] || {}).code || "-").join(" / ");
    html += `<tr><td>${esc(c.id)}</td><td>${esc(c.chapter)}</td><td>${esc(c.section)}</td><td>${esc(c.title)}</td><td>${codes}</td><td>${c.validated ? "✅" : "⏳"}</td></tr>`;
  }
  html += "</table></div>";
  app.innerHTML = html;
}

window.addEventListener("hashchange", () => { viewStars = null; route(); });
boot().catch(e => { app.innerHTML = `<p style="color:red">Erreur: ${esc(e.message)}</p>`; });
