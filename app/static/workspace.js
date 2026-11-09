(function () {
  "use strict";
  const { state, esc, date, api, render, dialog, meter, $, photoCredit } = HPA;
  const G = HPA.guide;
  const { steps, question } = G;
  const short = {
    TODO: "À traiter",
    IN_PROGRESS: "En cours",
    EVIDENCE_MISSING: "Preuve manquante",
    NON_COMPLIANT: "Non conforme",
    VALIDATED: "Validé",
  };
  const tones = { VALIDATED: "green", IN_PROGRESS: "blue", EVIDENCE_MISSING: "amber", NON_COMPLIANT: "red" };
  const view = {
    audit: null,
    evidences: [],
    history: [],
    criteria: [],
    score: null,
    reachable: null,
    stars: null,
    step: "overview",
    cid: null,
    search: "",
    filter: "",
    ajo: false,
  };
  const tag = (key) => `<span class="pill ${tones[key] || ""}">${esc(short[key] || key)}</span>`;
  const base = () => "/api/audits/" + view.audit.id;
  const link = (step = "overview", cid = "") => `#/dossier/${view.audit.id}/${step}${cid ? "/" + cid : ""}`;
  const meta = () => state.meta;
  const flow = () => view.audit.workflow;
  const activeRows = (key) => view.criteria.filter(c => c.code !== "NA" && G.stepOf(c) === key).sort((a,b) => Number(a.id)-Number(b.id));
  const continueLink = () => G.entry(flow(), link);

  function list(audits) {
    render(
      `<div class="wrap"><section class="dashcover"><div><div class="eyebrow light"><i></i>Espace invité</div><h1>Mes dossiers</h1><p>${audits.length ? `${audits.length} dossier${audits.length > 1 ? "s" : ""} de classement` : "Préparez le classement de votre établissement."}</p></div>${photoCredit}</section><div class="sectionhead"><h2>${audits.length ? "Dossiers en préparation" : "Votre premier dossier"}</h2><button data-act="create">＋ Nouveau dossier</button></div>${
        audits.length
          ? `<div class="dossier-grid">${audits
              .map((a) => {
                const progress = a.applicable ? Math.round((100 * a.filled) / a.applicable) : 0;
                return `<article class="panel dossiercard"><div class="splitline"><span class="foldericon" aria-hidden="true"><img src="/static/dossier.png" width="30" height="30" alt=""></span><span class="star-tag">${a.target_stars} ★ <span>visées</span></span></div><p class="eyebrow">${a.type === "prl" ? "Parc résidentiel de loisirs" : "Camping"} · ${esc(a.mention)}</p><h3><a href="#/dossier/${a.id}">${esc(a.name)}</a></h3><div class="splitline"><span>Critères renseignés</span><b>${progress} %</b></div>${meter(a.filled, a.applicable)}<p class="meta">${a.filled} sur ${a.applicable} applicables</p><p class="card-stage">Étape ${a.workflow.number}/5 · ${esc(G.label(a.workflow.current))}</p><div class="last"><strong>Dernière activité</strong><span>${esc(a.last_event?.message || "Dossier créé.")}</span><small>${date(a.last_event?.created_at || a.updated_at)}</small></div><div class="cardfoot"><a class="button" href="#/dossier/${a.id}">Ouvrir le dossier <span>→</span></a><button class="textbtn danger" data-delete="${a.id}">Supprimer</button></div></article>`;
              })
              .join(
                "",
              )}</div><button class="textbtn demo-link" data-act="sample">Explorer un exemple 3 étoiles →</button>`
          : `<div class="onboard"><article class="panel"><div class="foldericon">＋</div><h3>Créer mon premier dossier</h3><p>Renseignez le profil de votre camping pour découvrir les critères qui s’appliquent.</p><button data-act="create">Créer mon premier dossier →</button></article><article class="panel"><div class="foldericon">☆</div><h3>Explorer un exemple 3 étoiles</h3><p>Visitez la Clairière Bleue avec sept critères déjà renseignés et trois justificatifs conservés.</p><button class="secondary" data-act="sample">Explorer l’exemple →</button></article></div>`
      }</div>`,
    );
    view.list = audits;
  }
  function fields(a) {
    const select = (key, label, options) =>
      `<label>${label}<select name="${key}">${options.map(([v, t]) => `<option value="${v}" ${String(a[key]) === String(v) ? "selected" : ""}>${t}</option>`).join("")}</select></label>`;
    return `<label>Nom de l’établissement<input name="name" required maxlength="180" value="${esc(a.name || "")}" placeholder="Nom du camping"></label><div class="formgrid">${select(
      "type",
      "Type d’établissement",
      [
        ["camping", "Camping"],
        ["prl", "Parc résidentiel de loisirs"],
      ],
    )}${select("mention", "Mention", [
      ["tourisme", "Tourisme"],
      ["loisirs", "Loisirs"],
    ])}${select(
      "target_stars",
      "Catégorie visée",
      [1, 2, 3, 4, 5].map((v) => [v, `${v} étoile${v > 1 ? "s" : ""}`]),
    )}</div>`;
  }
  function create() {
    dialog(
      `<div class="eyebrow"><i></i>Nouveau dossier</div><h2>Votre établissement ${question("profile")}</h2><p>Créez le dossier, puis complétez son profil à l’étape 1.</p><form id="create-audit">${fields({ type: "camping", mention: "tourisme", target_stars: 3 })}<button>Créer le dossier →</button><p data-feedback role="status"></p></form>`,
    );
  }
  function profile() {
    const a = view.audit,
      p = a.profile;
    return `<section class="panel"><div class="section-kicker">ÉTAPE 1 SUR 5</div><h2>Profil de l’établissement ${question("profile")}</h2><p>Indiquez au minimum le nombre total d’emplacements. Les équipements connus permettent d’adapter la liste des critères.</p><form id="profile-form">${fields(a)}<h3>Emplacements et services</h3><div class="formgrid">${meta()
      .profile_fields.map(
        (f) =>
          `<label>${esc(f.label)}${f.type === "number" ? `<input name="pf_${f.key}" type="number" min="0" step="1" placeholder="À préciser" value="${esc(p[f.key] ?? "")}">` : `<select name="pf_${f.key}"><option value="">À préciser</option><option value="true" ${p[f.key] === true ? "selected" : ""}>Oui</option><option value="false" ${p[f.key] === false ? "selected" : ""}>Non</option></select>`}</label>`,
      )
      .join(
        "",
      )}</div><div class="guide-actions"><button value="advance">Confirmer le profil et continuer →</button><button class="secondary" value="draft">Enregistrer sans avancer</button></div><p data-feedback role="status"></p></form></section>`;
  }
  function history() {
    return `<section class="panel"><div class="sectionhead tight"><h2>Fil chronologique</h2><span class="meta">${view.history.length} activité${view.history.length > 1 ? "s" : ""}</span></div>${view.history.length ? `<ol class="timeline">${view.history.map(e => {
      const c = view.criteria.find(row => row.id === e.criterion_id);
      const key = c ? G.stepOf(c) : e.step;
      const available = c ? flow().allowed_ids.includes(c.id) : (key === "overview" || flow().open_steps.includes(key));
      return `<li><i aria-hidden="true"></i><div><time>${date(e.created_at)}</time>${available ? `<a href="${link(key, c?.id || "")}">${esc(e.message)}</a>` : `<span>${esc(e.message)}</span>`}</div></li>`;
    }).join("")}</ol>` : "<p>Les actions enregistrées apparaîtront ici.</p>"}</section>`;
  }
  function metrics() {
    const a = view.audit,
      s = view.score;
    return `<div class="metrics"><div><span>Critères renseignés</span><strong>${a.filled} <small>/ ${a.applicable}</small></strong>${meter(a.filled, a.applicable)}</div><div><span>Points obligatoires</span><strong>${s.x.obtained} <small>/ ${s.x.total}</small></strong><progress class="reg-meter" max="${s.x.total || 1}" value="${s.x.obtained}" aria-label="Points obligatoires"></progress><small>Seuil de 95 %</small></div><div><span>Points à la carte</span><strong>${s.o.obtained} <small>pts</small></strong><progress class="reg-meter" max="${Math.max(s.o.required ?? s.o.base_required, 1)}" value="${s.o.obtained}" aria-label="Points à la carte obtenus par rapport au seuil"></progress><small>${s.o.required === null ? "Seuil de base · " + s.o.base_required + " pts" : s.o.required + " pts requis"}</small></div></div>`;
  }
  function overview() {
    const g = flow(), c = view.criteria.find(row => row.id === g.next_id);
    const title = c ? `Critère ${c.id} · ${esc(c.title)}` : ({profile:"Décrire l’établissement", proofs:"Relire les justificatifs", summary:"Consulter la synthèse"})[g.current];
    const action = c ? `Reprendre au critère ${c.id}` : ({profile:"Compléter le profil",proofs:"Vérifier les pièces",summary:"Ouvrir la synthèse"})[g.current];
    return `<section class="resume"><div><div class="eyebrow light"><i></i>À poursuivre · Étape ${g.number} sur 5</div><h2>${title}</h2><p>${c ? "C’est le premier critère applicable qui reste à traiter." : "Votre avancement est enregistré dans ce dossier."}</p></div><a class="button white" href="${continueLink()}">${action} →</a></section>${metrics()}<div class="detailgrid">${history()}<aside class="panel next"><div class="eyebrow"><i></i>Votre guide</div><h2>Un critère à la fois ${question("journey")}</h2><p>Suivez les numéros proposés. Les étapes déjà parcourues restent accessibles pour corriger ou compléter une réponse.</p></aside></div>`;
  }
  function proofBlock(c) {
    const files = view.evidences.filter((e) => e.criterion_id === c.id);
    return `<div class="proofblock"><h3>Justificatifs <small>${files.length}</small> ${question("evidence")}</h3>${files.map((e) => `<article class="proofitem"><div><span class="type">${esc(e.kind)}</span><a href="${base()}/evidence/${e.id}/file" target="_blank" rel="noopener">${esc(e.original_name || e.url)}</a>${e.stale ? '<span class="pill amber">À rafraîchir</span>' : ""}</div><form class="caption-form inline" data-id="${e.id}"><input name="caption" aria-label="Légende" maxlength="1000" placeholder="Ajouter une légende" value="${esc(e.caption)}"><button class="secondary">Enregistrer la légende</button></form><div class="tools"><button class="textbtn" data-stale="${e.id}" data-value="${e.stale ? 0 : 1}">${e.stale ? "Marquer à jour" : "Marquer à rafraîchir"}</button><button class="textbtn danger" data-remove-proof="${e.id}">Retirer</button></div></article>`).join("")}<form class="upload-form" data-cid="${c.id}"><label>Ajouter des photos ou des documents<input type="file" name="files" multiple required></label><button class="secondary">Envoyer les fichiers</button><progress max="100" value="0" hidden aria-label="Progression de l’envoi"></progress><p data-feedback role="status"></p></form><form class="url-form inline" data-cid="${c.id}"><input type="url" aria-label="Adresse du justificatif" name="url" placeholder="https://…" required><button class="secondary">Ajouter un lien</button><p data-feedback role="status"></p></form></div>`;
  }
  function critBody(c) {
    const source = state.ref?.meta?.source_url || "";
    return `<div class="critbody">${c.exigence ? `<p class="require"><strong>Exigence en ${view.stars}★</strong> · ${esc(c.exigence)}</p>` : ""}${c.precisions ? `<p>${esc(c.precisions)}</p>` : ""}${source && c.source_page ? `<a class="textlink" href="${esc(source)}#page=${Number(c.source_page)}" target="_blank" rel="noopener">Tableau Atout France · p. ${c.source_page} ↗</a>` : ""}${c.via ? `<p>Validé par le critère ${esc(c.via)}.</p>` : ""}<h3>Votre constat ${question("status")}</h3><form class="criterion-form" data-cid="${c.id}"><div class="formgrid"><label>Statut<select name="status">${Object.entries(
      meta().status_labels,
    )
      .map(([k, v]) => `<option value="${k}" ${k === c.status ? "selected" : ""}>${esc(v)}</option>`)
      .join(
        "",
      )}</select></label><label>Validé par<input name="validated_by" maxlength="160" value="${esc(c.validated_by)}"></label>${c.points_min ? `<label>Bonification obtenue<select name="awarded_points"><option value="">À préciser</option>${[1, 2, 3, 4, 5].map((n) => `<option ${c.awarded_points === n ? "selected" : ""} value="${n}">${n} pt</option>`).join("")}</select></label>` : ""}</div><label>Notes internes<textarea name="notes" maxlength="30000" rows="3">${esc(c.notes)}</textarea></label><div class="guide-actions"><button value="advance">Enregistrer et continuer →</button><button class="secondary" value="draft">Enregistrer sans avancer</button></div><p data-feedback role="status"></p></form>${proofBlock(c)}</div>`;
  }
  const matchText = (a, b) =>
    a
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase()
      .includes(
        b
          .normalize("NFD")
          .replace(/\p{Diacritic}/gu, "")
          .toLowerCase(),
      );
  function rows() {
    const allowed = new Set(flow().allowed_ids);
    const matched = activeRows(view.step).filter(c => (!view.search || matchText(c.id+" "+c.title,view.search)) && (!view.filter || c.status === view.filter) && (!view.ajo || c.ajo));
    if (!matched.length) return "<p>Aucun critère ne correspond aux filtres.</p>";
    return `<ol class="ordered-index">${matched.map(c => {
      const contents = `<b>${esc(c.id)}</b><span>${esc(c.title)}</span>`;
      return allowed.has(c.id) ? `<li><a href="${link(view.step,c.id)}" ${c.id === view.cid ? 'aria-current="true"' : ""}>${contents}<small>${esc(short[c.status])}</small></a></li>` : `<li><span class="index-locked" aria-disabled="true">${contents}<small>${G.lock} Verrouillé</small></span></li>`;
    }).join("")}</ol>`;
  }
  function criteria() {
    const key = view.step, g = flow(), group = activeRows(key), i = group.findIndex(c => c.id === view.cid), c = group[i];
    const counts = g.counts[key];
    const title = key === "prerequisites" ? "Prérequis au classement" : "Critères du classement";
    const progress = `<div class="guided-progress"><span>${counts.filled} sur ${counts.total} renseignés</span><progress value="${counts.filled}" max="${counts.total || 1}" aria-label="Avancement de cette étape"></progress></div>`;
    const index = `<details class="guide-index panel"><summary>Parcourir la liste des ${key === "prerequisites" ? "prérequis" : "critères"} (${group.length})</summary><p class="meta">Les numéros à venir s’ouvrent dans l’ordre. Les réponses précédentes restent modifiables.</p><div class="filters"><label>Rechercher<input id="criterion-search" type="search" placeholder="Numéro ou intitulé" value="${esc(view.search)}"></label><label>Statut<select id="criterion-filter"><option value="">Tous les statuts</option>${Object.entries(short).map(([v,t])=>`<option value="${v}" ${v === view.filter ? "selected" : ""}>${t}</option>`).join("")}</select></label><label class="check"><input id="ajo-filter" type="checkbox" ${view.ajo ? "checked" : ""}> Justificatif obligatoire</label></div><div id="criterion-list">${rows()}</div></details>`;
    return `<section><header class="guide-section-head"><div><div class="section-kicker">ÉTAPE ${key === "prerequisites" ? 2 : 3} SUR 5</div><h2>${title} ${question(key)}</h2></div>${progress}</header>${c ? `<article class="criterion guided-sheet" id="criterion-${c.id}"><div class="sheet-heading"><div class="sheet-meta"><span class="official-number">Critère n° ${esc(c.id)}</span><span>Fiche ${i+1} sur ${group.length}</span>${tag(c.status)}</div><h2>${esc(c.title)} ${G.criterionQuestion(c)}</h2><p>${esc(c.code)} · ${c.points} point${c.points > 1 ? "s" : ""}${c.ajo ? " · Justificatif obligatoire pour valider" : ""}</p></div>${critBody(c)}</article><div class="sheet-links">${i>0 ? `<a href="${link(key,group[i-1].id)}">← Revoir le critère ${group[i-1].id}</a>` : ""}${c.id !== g.next_id ? `<a href="${continueLink()}">Reprendre le parcours →</a>` : ""}</div>` : `<p class="panel">Aucun critère ne s’applique à cette étape. <a href="${continueLink()}">Continuer →</a></p>`}${index}</section>`;
  }
  function proofs() {
    const grouped = view.criteria.filter(c => c.nb_evidences || (c.code !== "NA" && c.status === "EVIDENCE_MISSING"));
    const missing = grouped.filter(c => c.code !== "NA" && c.status === "EVIDENCE_MISSING").length;
    const stale = view.evidences.filter(e => e.stale).length;
    return `<section class="panel"><div class="section-kicker">ÉTAPE 4 SUR 5</div><h2>Relire les justificatifs ${question("proofs")}</h2><p>Ouvrez les pièces et vérifiez qu’elles correspondent au bon critère. Un manque peut rester signalé dans votre bilan.</p><p class="proof-tally">Pièces jointes : <b>${view.evidences.length}</b> · À rafraîchir : <b>${stale}</b> · Critères signalés « Preuve manquante » : <b>${missing}</b></p>${grouped.map(c => {
      const label = `Critère ${c.id} · ${esc(c.title)}`;
      return `<article class="proofrow"><div>${c.code === "NA" ? `<strong>${label} (hors profil)</strong>` : `<a class="textlink" href="${link(G.stepOf(c),c.id)}">${label}</a>`}${view.evidences.filter(e=>e.criterion_id===c.id).map(e=>`<p><span class="type">${esc(e.kind)}</span><a target="_blank" rel="noopener" href="${base()}/evidence/${e.id}/file">${esc(e.original_name)}</a>${e.stale ? " · À rafraîchir" : ""}</p>`).join("")}</div>${tag(c.status)}</article>`;
    }).join("") || "<p>Aucune pièce jointe à ce dossier.</p>"}<form id="proof-review"><label class="review-check"><input name="reviewed" type="checkbox" required> J’ai vérifié les pièces et pris connaissance des éventuels manques.</label><button>Confirmer la revue et ouvrir la synthèse →</button><p data-feedback role="status"></p></form></section>`;
  }
  function simulatedCriteria() {
    if (view.stars === view.audit.target_stars) return "";
    const changed = view.criteria.filter(
      (c) =>
        c.code !== "NA" &&
        c.rules?.[view.stars]?.exigence &&
        c.rules[view.stars].exigence !== c.rules?.[view.audit.target_stars]?.exigence,
    );
    if (!changed.length) return "";
    return `<details class="compared"><summary>Exigences différentes en ${view.stars}★ · ${changed.length} critères</summary>
            ${changed
              .map(
                (c) => `<div class="proofrow"><div><strong>Critère ${esc(c.id)} · ${esc(c.title)}</strong>
            <p>${view.audit.target_stars}★ : ${esc(c.rules[view.audit.target_stars]?.exigence || "—")} · ${view.stars}★ : ${esc(c.exigence)}</p></div>${tag(c.status)}</div>`,
              )
              .join("")}</details>`;
  }
  function summary() {
    const a = view.audit,
      s = view.score;
    return `<section class="panel"><div class="sectionhead tight"><div><div class="eyebrow"><i></i>Simulation</div><h2>Résultat en ${view.stars} étoiles ${question("summary")}</h2></div><div class="stars">${[1, 2, 3, 4, 5].map((n) => `<button data-stars="${n}" aria-pressed="${view.stars === n}">${n}★</button>`).join("")}</div></div><p class="intro">${s.eligible ? "Éligible selon les éléments renseignés." : "Classement actuellement non éligible."}</p><p>Catégorie visée · ${a.target_stars}★. Étoiles atteignables · ${
      Object.entries(view.reachable || {})
        .filter((x) => x[1])
        .map((x) => x[0] + "★")
        .join(", ") || "aucune"
    }.</p>${metrics()}${simulatedCriteria()}<p>${s.x.pending} points obligatoires en attente · ${s.x.lost} points non conformes · ${s.o.compensation === null ? "Compensation à déterminer." : s.o.compensation + " points de compensation."}</p>${s.blockers.map((b) => `<article class="blocker"><strong>${esc(b.message)}</strong><p>${b.criteria.map((id) => `<a href="${link(view.criteria.find((c) => c.id === id)?.chapter === 0 ? "prerequisites" : "criteria", id)}">Critère ${esc(id)}</a>`).join(" · ")}</p></article>`).join("")}<div class="tools"><a class="button" href="${base()}/export/zip?stars=${view.stars}">Télécharger le ZIP ↓</a><a class="button secondary" target="_blank" rel="noopener" href="${base()}/export/book?stars=${view.stars}">Synthèse à imprimer ↗</a></div></section>`;
  }
  function draw() {
    const a = view.audit,
      step = view.step,
      labels = Object.fromEntries(steps);
    const sections = { overview, profile, prerequisites: criteria, criteria, proofs, summary };
    render(
      `<div class="wrap dossier"><div class="crumb"><a href="/espace">Mes dossiers</a> <span>›</span> <a href="${link()}">Vue d’ensemble</a>${step !== "overview" ? " <span>›</span> " + labels[step] : ""}</div><div class="dtitle"><div><div class="eyebrow"><i></i>${a.type === "prl" ? "Parc résidentiel de loisirs" : "Camping"} · ${esc(a.mention)}</div><h1>${esc(a.name)}</h1></div><span class="star-tag">${a.target_stars} ★ visées</span></div>${G.nav(flow(),step,link)}${(sections[step] || overview)()}<footer><a href="${link()}">Vue d’ensemble</a><button class="textbtn" data-act="clone">Dupliquer ce dossier</button></footer></div>`,
    );
  }
  HPA.workspace = { steps, view, short, link, base, list, create, profile, rows, draw };
})();
