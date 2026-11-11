(() => {
  "use strict";
  const grid = JSON.parse(document.getElementById("starter-grid").textContent);
  const byId = id => document.getElementById(id);
  const store = window.HpaDraft;
  const profile = byId("starter-profile"), sheet = byId("starter-sheet"), request = byId("starter-request");
  const saveState = byId("save-state");
  const guides = {
    "1": ["Capacité d’accueil", "Vérifiez si votre terrain peut accueillir plus de vingt personnes ou plus de six hébergements de plein air."],
    "2": ["Permis d’aménager et emplacements", "Comparez la capacité autorisée par le permis avec le nombre d’emplacements exploités et celui déclaré pour le classement."],
    "3": ["Exploitation du parc sous régime hôtelier", "Vérifiez qui détient la propriété ou la jouissance du terrain et qui en assure l’exploitation."],
    "4": ["Enseigne et signalétique", "Faites le tour des panneaux de l’entrée et des allées. Vérifiez leur propreté, leur état et leur lisibilité."]
  };
  const labels = {IN_PROGRESS:"En cours", EVIDENCE_MISSING:"Preuve manquante", NON_COMPLIANT:"Non conforme", VALIDATED:"Validé"};
  const sections = ["profile-step","sheet-step","summary-step","mini-demande"];
  let draft = store.read(), index = 0;
  const retry = byId("mini-demande").dataset.retry === "yes";
  if (!draft && retry && request.elements.draft.value) {
    try { draft = {...JSON.parse(request.elements.draft.value), ready:true}; } catch { /* Start again with the profile. */ }
  }
  function newDraft() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return {id:Array.from(bytes, byte => byte.toString(16).padStart(2,"0")).join(""), reference:grid.reference,
      type:"camping", mention:"tourisme", stars:3, pitches:null, answers:{}, ready:false};
  }
  function routes(value = draft) {
    return grid.paths[[value?.type,value?.mention,value?.stars].join("/")] || [];
  }
  function title(row) { return guides[row.id]?.[0] || grid.sheets[row.id]; }
  function filled() { return routes().filter(row => draft.answers?.[row.id]).length; }
  function persist() {
    saveState.textContent = store.write(draft) ? "Enregistré dans ce navigateur." :
      "Sauvegarde indisponible dans ce navigateur. Gardez cette page ouverte. Vous pourrez joindre le brouillon à votre demande.";
    recap();
  }
  function recap() {
    const n = draft?.ready ? filled() : 0;
    byId("draft-progress").textContent = n + " sur 3 fiches renseignées";
    document.querySelector(".starter-side progress").value = n;
    byId("profile-recap").textContent = draft?.ready ? (draft.type === "prl" ? "PRL" : "Camping") +
      " · " + draft.pitches + " emplacements · " + draft.stars + " ★" : "Profil à confirmer";
    byId("forget").hidden = !draft;
  }
  function show(id, focus = true) {
    sections.forEach(section => { byId(section).hidden = section !== id; });
    if (focus) byId(id).querySelector("h2").focus();
  }
  function restoreFields() {
    if (draft) for (const name of ["type","mention","stars","pitches"]) profile.elements[name].value = draft[name] ?? "";
    else profile.reset();
  }
  function fields() {
    return {type:profile.elements.type.value, mention:profile.elements.mention.value,
      stars:Number(profile.elements.stars.value), pitches:profile.elements.pitches.valueAsNumber || null};
  }
  function drawSheet(position, focus = true) {
    const rows = routes();
    if (position >= rows.length) { drawSummary(focus); return; }
    index = position;
    const row = rows[index];
    byId("sheet-number").textContent = "Fiche " + (index+1) + " sur " + rows.length + " · Critère " + row.id;
    byId("sheet-title").textContent = title(row);
    byId("official-wording").textContent = grid.sheets[row.id];
    byId("sheet-guide").textContent = (guides[row.id]?.[1] || "") + (row.proof ?
      " La validation demande un justificatif. Vous pourrez le joindre dans votre espace invité." : "");
    byId("choices").replaceChildren();
    for (const [value, text] of Object.entries(labels)) {
      if (row.proof && value === "VALIDATED") continue;
      const label = document.createElement("label"), input = document.createElement("input");
      label.className = "choice"; input.type = "radio"; input.name = "answer";
      input.value = value; input.required = true; input.checked = draft.answers[row.id] === value;
      label.append(input, document.createTextNode(text)); byId("choices").append(label);
    }
    byId("sheet-step").querySelector("details").open = false;
    show("sheet-step",focus);
  }
  function drawSummary(focus = true) {
    byId("answer-list").replaceChildren();
    const rows = routes();
    for (const row of rows) {
      const li = document.createElement("li"), strong = document.createElement("strong");
      strong.textContent = labels[draft.answers[row.id]] || "À traiter";
      li.append(document.createTextNode(title(row)),strong); byId("answer-list").append(li);
    }
    byId("summary-profile").textContent = byId("profile-recap").textContent;
    const missing = rows.find(row => draft.answers[row.id] === "EVIDENCE_MISSING");
    byId("next-action").textContent = missing ? "À préparer pour la suite : " +
      (missing.id === "2" ? "retrouvez votre permis d’aménager." : "réunissez une pièce pour « " + title(missing) + " ».") :
      "Votre invitation vous permettra de poursuivre les fiches suivantes et de joindre vos justificatifs.";
    show("summary-step",focus);
  }
  function resume(focus = false) {
    restoreFields(); recap();
    if (!draft?.ready || !routes().length) { show("profile-step",focus); return; }
    drawSheet(filled(),focus);
  }
  profile.addEventListener("input", () => {
    if (draft?.ready) return;
    draft ||= newDraft();
    Object.assign(draft, fields()); persist();
  });
  profile.addEventListener("submit", event => {
    event.preventDefault();
    draft ||= newDraft();
    const first = !draft.ready, old = draft.answers || {};
    Object.assign(draft, fields(), {ready:true, answers:{}, reference:grid.reference});
    for (const row of routes()) {
      if (!Object.hasOwn(labels,old[row.id]) || (row.proof && old[row.id] === "VALIDATED")) break;
      draft.answers[row.id] = old[row.id];
    }
    persist();
    if (first) store.count("start",request.elements.csrfmiddlewaretoken.value);
    drawSheet(filled());
  });
  sheet.addEventListener("submit", event => {
    event.preventDefault();
    draft.answers[routes()[index].id] = new FormData(sheet).get("answer"); persist(); drawSheet(index+1);
  });
  byId("back-sheet").onclick = () => index ? drawSheet(index-1) : show("profile-step");
  byId("edit-summary").onclick = () => drawSheet(0);
  byId("open-request").onclick = event => { event.preventDefault(); show("mini-demande"); };
  request.addEventListener("submit", async event => {
    event.preventDefault();
    const attached = request.elements.attach.checked;
    if (attached && !draft?.ready) { show("profile-step"); return; }
    request.elements.draft.disabled = !attached;
    request.elements.draft.value = attached ? JSON.stringify(store.packet(draft)) : "";
    const submitter = request.querySelector("button");
    const feedback = byId("request-feedback");
    if (submitter.disabled) return;
    feedback.hidden = true;
    submitter.disabled = true; submitter.textContent = "Envoi en cours…";
    try {
      const response = await fetch(request.action, {method:"POST", body:new URLSearchParams(new FormData(request)),
        credentials:"same-origin"});
      if (response.ok && response.redirected) {
        location.assign("/?demande=recue#acces");
        return;
      }
      const reply = new DOMParser().parseFromString(await response.text(), "text/html");
      feedback.textContent = reply.querySelector(".form-error")?.textContent ||
        "La demande n’a pas abouti. Vérifiez les champs puis réessayez.";
    } catch {
      feedback.textContent = "L’envoi a été interrompu. Vérifiez votre connexion puis réessayez.";
    }
    feedback.hidden = false; submitter.disabled = false; submitter.textContent = "Réessayer l’envoi";
  });
  byId("forget").onclick = () => { byId("confirm-forget").hidden = false; byId("cancel-forget").focus(); };
  byId("cancel-forget").onclick = () => { byId("confirm-forget").hidden = true; byId("forget").focus(); };
  byId("yes-forget").onclick = () => {
    if (!store.erase(draft?.id)) { saveState.textContent = "Effacement impossible. Vérifiez les réglages de votre navigateur."; return; }
    draft = null; request.reset(); byId("confirm-forget").hidden = true; resume(true);
    saveState.textContent = "Brouillon effacé de ce navigateur.";
  };
  window.addEventListener("storage", event => {
    if (event.key === store.key || event.key === null) { draft = store.read(); resume(); }
  });
  window.addEventListener("pageshow", () => {
    const submitter = request.querySelector("button"); submitter.disabled = false; submitter.textContent = "Envoyer ma demande →";
  });
  byId("starter-app").hidden = false;
  if (draft && (draft.reference !== grid.reference || !draft.answers || typeof draft.answers !== "object")) {
    draft.ready = false; draft.answers = {}; saveState.textContent = "Vérifiez de nouveau le profil pour utiliser la grille actuelle.";
  }
  resume(); if (retry) show("mini-demande");
})();
