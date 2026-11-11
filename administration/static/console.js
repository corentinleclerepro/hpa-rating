(function () {
  "use strict";
  const { state, esc, date, $, api, busy, render, dialog, close, toast, showErr } = HPA;
  function header() {
    $(".bar .logout-button").hidden = !state.session?.admin;
  }
  function split(title, description, form) {
    return `<div class="entry"><section class="panel gateform"><div class="eyebrow"><i></i>Espace administration</div><h1>${title}</h1><p class="intro">${description}</p>${form}</section></div>`;
  }
  function adminGate(recovery = false) {
    const setup = state.session.setup_required;
    const button = setup || !recovery ? "Recevoir un code par e-mail" : "Ouvrir l’administration";
    render(
      split(
        setup ? "Activer l’administration" : "Connexion à l’administration",
        setup
          ? "Saisissez votre clé d’activation et choisissez un mot de passe. Nous vous enverrons ensuite un code par e-mail."
          : recovery ? "Saisissez votre mot de passe et l’un de vos codes de secours."
            : "Saisissez votre mot de passe pour recevoir un code dans la boîte e-mail de l’administration.",
        `<form id="${setup ? "setup-start" : "admin-login"}">
          ${setup ? '<label>Clé d’activation<input name="ticket" type="password" autocomplete="off" required></label>' : ""}
          <label>${setup ? "Choisissez un mot de passe" : "Mot de passe"}<input name="password" type="password"
            autocomplete="${setup ? "new-password" : "current-password"}" ${setup ? 'minlength="12" placeholder="12 caractères minimum"' : ""} required></label>
          ${recovery ? '<label>Code de secours<input name="recovery" autocomplete="one-time-code" maxlength="16" required></label>' : ""}
          <button class="wide">${button} <span aria-hidden="true">→</span></button>
          <p data-feedback role="status"></p></form>
          ${setup ? "" : `<button type="button" class="textbtn" data-access="${recovery ? "use-email" : "use-recovery"}">${recovery ? "Recevoir un code par e-mail" : "Utiliser un code de secours"}</button>`}`,
      ),
    );
  }
  function emailStep(stage) {
    render(
      split(
        "Vérifiez votre e-mail",
        "Entrez les six chiffres envoyés par Hpa Rating. Le code est valable 10 minutes dans ce navigateur.",
        `<form id="${stage === "setup" ? "setup-finish" : "login-finish"}">
          <label>Code reçu par e-mail<input name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required></label>
          <button class="wide">${stage === "setup" ? "Activer l’administration" : "Ouvrir l’administration"}</button>
          <button type="button" class="secondary" data-access="resend-email">Renvoyer le code</button>
          <p data-feedback role="status"></p></form>
          <button type="button" class="textbtn" data-access="use-email">Revenir à la première étape</button>`,
      ),
    );
    $("input[name=code]").focus();
  }
  function requestRow(entry) {
    const pending = entry.status === "pending";
    const status = { pending: "À traiter", approved: "Acceptée", declined: "Refusée" }[entry.status];
    return `<article class="invit"><div><strong>${esc(entry.camping)}</strong><span class="pill">${status}</span>
      <p class="request-email">${esc(entry.email)}</p><p class="meta">Reçue le ${date(entry.created_at)}</p></div>
      ${pending ? `<div class="tools"><button data-access="approve" data-id="${esc(entry.id)}">Accepter et créer un code</button>
        <button class="secondary" data-access="decline" data-id="${esc(entry.id)}">Refuser et effacer la demande</button></div>` : ""}</article>`;
  }
  async function adminPanel() {
    const [{ guests }, { requests }] = await Promise.all([api("/api/admin/invitations"), api("/api/admin/demandes")]);
    const pending = requests.filter(entry => entry.status === "pending");
    const history = requests.filter(entry => entry.status !== "pending");
    render(
      `<div class="wrap"><div class="eyebrow"><i></i>Administration</div><h1>Demandes et invitations</h1>
      <section class="panel inbox"><h2>Demandes à traiter <small>${pending.length}</small></h2>
        ${pending.length ? pending.map(requestRow).join("") : "<p>Aucune demande en attente.</p>"}
        ${history.length ? `<details><summary>Demandes traitées (${history.length})</summary>${history.map(requestRow).join("")}</details>` : ""}
      </section><div class="admin-grid"><section class="panel"><h2>Inviter directement</h2><form id="invite-create"><label>Nom ou adresse e-mail<input name="label" required maxlength="160" placeholder="Nom du destinataire"></label><button>Générer un code</button><p data-feedback role="status"></p></form></section><section class="panel"><h2>Invitations <small>${guests.length}</small></h2>${guests.length ? guests.map((g) => `<article class="invit"><div><strong>${esc(g.label)}</strong><span class="pill ${g.revoked ? "red" : g.code_used ? "green" : ""}">${g.revoked ? "Révoqué" : g.code_used ? "Actif" : "Jamais utilisé"}</span><p class="meta">Dernière utilisation · ${date(g.last_seen)}</p></div><div class="tools"><button class="secondary" data-access="rotate" data-id="${g.id}">Remplacer</button>${g.revoked ? "" : `<button class="textbtn danger" data-access="revoke" data-id="${g.id}">Révoquer</button>`}</div></article>`).join("") : "<p>Aucune invitation créée.</p>"}</section></div></div>`,
    );
    void showStarterStats();
  }
  async function showStarterStats() {
    const host = document.querySelector(".admin-grid");
    const panel = document.createElement("section");
    panel.className = "panel inbox";
    panel.setAttribute("aria-label", "Suivi du mini-dossier");
    host.before(panel);
    panel.innerHTML = "<h2>Suivi du mini-dossier</h2><p role='status'>Chargement des statistiques…</p>";
    try {
      const counts = await api("/api/admin/parcours");
      const cells = [["Affichages de l’accueil",counts.home],["Brouillons commencés",counts.start],
        ["Demandes depuis le brouillon",counts.request],["Dossiers poursuivis",counts.continued]];
      const rate = counts.home ? (100*counts.continued/counts.home).toLocaleString("fr-FR",{maximumFractionDigits:1}) : null;
      panel.innerHTML = '<h2>Suivi du mini-dossier <small>30 derniers jours</small></h2><dl class="funnel">' +
        cells.map(([label,n]) => "<div><dt>" + label + "</dt><dd>" + Number(n) + "</dd></div>").join("") +
        '</dl><p>' + (rate === null ? 'Le ratio sera disponible après le premier affichage de l’accueil.' :
          '<strong>' + rate + '</strong> dossiers poursuivis pour 100 affichages de l’accueil.') +
        '</p><p class="meta">Un dossier est compté une seule fois, au premier nouveau critère renseigné après la reprise. Les affichages incluent les retours sur l’accueil.</p>';
    } catch {
      panel.querySelector('[role="status"]').textContent = "Les statistiques sont momentanément indisponibles.";
    }
  }
  function issued(code, loginUrl, email = "") {
    const invite = `Bonjour,\n\nVoici votre accès personnel à Hpa Rating · Camp Compagnon.\n\nMon espace : ${loginUrl}\nCode personnel : ${code}\n\nConservez ce code pour retrouver vos dossiers à chaque visite.`;
    dialog(
      `<div class="eyebrow">Invitation personnelle</div><h2>Le code est prêt.</h2>${email ? `<p>À envoyer à <strong>${esc(email)}</strong>.</p>` : ""}<p>Copiez l’invitation maintenant. Ce code est affiché une seule fois.</p><textarea id="invitation-text" readonly rows="7">${esc(invite)}</textarea>${["localhost", "127.0.0.1"].includes(new URL(loginUrl).hostname) ? '<p class="hint">En essai local, ce lien ouvre l’application sur cet ordinateur.</p>' : ""}<button data-access="copy">Copier l’invitation</button>`,
    );
  }
  async function submit(form) {
    const body = Object.fromEntries(new FormData(form));
    const button = form.querySelector("button:not([type=button])");
    await busy(
      button,
      async () => {
        if (form.id === "admin-login") {
          const result = await api("/api/admin/login", "POST", body);
          if (result.email_pending) emailStep(result.email_pending); else await route();
          return;
        }
        if (form.id === "setup-start") {
          const result = await api("/api/admin/setup/start", "POST", body);
          emailStep(result.email_pending);
          return;
        }
        if (form.id === "login-finish") {
          await api("/api/admin/login/confirm", "POST", body);
          await route();
          return;
        }
        if (form.id === "setup-finish") {
          const { recovery_codes } = await api("/api/admin/setup/finish", "POST", body);
          state.session = await api("/api/session");
          header();
          await adminPanel();
          dialog(
            `<h2>Vos codes de secours</h2><p>Conservez ces codes en lieu sûr. Si votre boîte e-mail est indisponible, chacun permet une connexion avec votre mot de passe.</p><textarea rows="8" readonly>${esc(recovery_codes.join("\n"))}</textarea><button data-act="close">J’ai conservé mes codes</button>`,
          );
          return;
        }
        if (form.id === "invite-create") {
          const result = await api("/api/admin/invitations", "POST", body);
          issued(result.code, result.login_url);
          await adminPanel();
        }
      },
      form.id === "admin-login" ? "Connexion…" : "Enregistrement…",
    );
  }
  async function action(button) {
    const op = button.dataset.access;
    if (op === "use-email" || op === "use-recovery") {
      adminGate(op === "use-recovery");
      return;
    }
    if (op === "resend-email") {
      await busy(button, async () => {
        await api("/api/admin/email/resend", "POST", {});
        const field = button.form.elements.code;
        field.value = ""; field.focus();
        toast("Nouveau code envoyé. Utilisez le dernier e-mail reçu.");
      }, "Envoi…");
      return;
    }
    if (op === "copy") {
      const text = $("#invitation-text");
      try {
        await navigator.clipboard.writeText(text.value);
        toast("Invitation copiée.");
      } catch {
        text.select();
        toast("Le texte est sélectionné. Utilisez Ctrl+C pour le copier.");
      }
      return;
    }
    const id = button.dataset.id;
    if (op === "decline") {
      dialog(`<h2>Refuser et effacer la demande ?</h2><p>Le nom du camping et son e-mail seront immédiatement effacés de la liste des demandes. Cette action est définitive.</p><button data-access="decline-request" data-id="${esc(id)}">Refuser et effacer la demande</button>`);
      return;
    }
    if (op === "approve" || op === "decline-request") {
      await busy(button, async () => {
        const result = await api(`/api/admin/demandes/${id}/${op === "approve" ? "approve" : "decline"}`, "POST", {});
        if (result.code) issued(result.code, result.login_url, result.email);
        else { close(); toast("Demande refusée et effacée."); }
        await adminPanel();
      });
      return;
    }
    if (op === "rotate" || op === "revoke") {
      dialog(
        `<h2>${op === "rotate" ? "Remplacer ce code ?" : "Révoquer cet accès ?"}</h2><p>L’ancien code et ses sessions seront invalidés. Les dossiers resteront disponibles lors d’une nouvelle invitation pour cet accès.</p><button data-access="confirm-${op}" data-id="${esc(id)}">${op === "rotate" ? "Remplacer le code" : "Révoquer l’accès"}</button>`,
      );
      return;
    }
    if (op.startsWith("confirm-")) {
      await busy(button, async () => {
        const result = await api(`/api/admin/invitations/${id}/${op.slice(8)}`, "POST", {});
        close();
        if (result.code) issued(result.code, result.login_url);
        else toast("Accès révoqué.");
        await adminPanel();
      });
    }
  }
  async function route() {
    try {
      state.session = await api("/api/session");
      header();
      if (state.session.admin) await adminPanel();
      else if (state.session.email_pending) emailStep(state.session.email_pending);
      else adminGate();
    } catch (e) { showErr(e); }
  }
  state.onHttpError = (status, path) => {
    if (status === 403 && state.session?.admin && path.startsWith("/api/admin/")) {
      state.session.admin = false;
      close();
      route();
    }
  };
  document.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(event.target);
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    try {
      if (button.dataset.access) await action(button);
      else if (button.dataset.act === "logout") await HPA.signOut(button, "/api/logout/admin", "/");
      else if (button.dataset.act === "close") close();
      else if (button.dataset.act === "retry") await route();
    } catch (e) { toast(e.message); }
  });
  window.addEventListener("pageshow", e => { if (e.persisted) { close(); route(); } });
  route();
})();
