(function () {
  "use strict";
  const { render, busy, api, photoCredit } = HPA;
  function split(title, description, form) {
    return `<div class="gate wrap"><section class="panel gateform"><div class="eyebrow"><i></i>Espace invité</div><h1>${title}</h1><p class="intro">${description}</p>${form}</section><aside class="gatephoto" aria-label="Camping en bord de mer, avec piscine et mobil-homes colorés">${photoCredit}</aside></div>`;
  }
  function guest() {
    render(
      split(
        "Retrouvez vos dossiers.",
        "Saisissez le code personnel que vous avez reçu par e-mail.",
        `<form id="guest-login"><label>Code personnel<input name="code" placeholder="HPA-…" autocomplete="current-password" type="password" required maxlength="100"></label><button class="primary wide">Ouvrir mon espace <span aria-hidden="true">→</span></button><p data-feedback class="feedback" role="status"></p></form>`,
      ),
    );
  }
  async function submit(form) {
    await busy(form.querySelector("button"), async () => {
      await api("/api/login", "POST", Object.fromEntries(new FormData(form)));
      location.assign("/espace" + (location.hash.startsWith("#/dossier/") ? location.hash : ""));
    }, "Connexion…");
  }
  HPA.access = { guest, submit };
})();
