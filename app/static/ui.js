(function () {
  "use strict";
  const { $, state, csrf } = HPA;
  Object.assign(state, { meta: null, ref: null, screen: 0 });
  state.onHttpError = (status, path) => {
    if (status === 401 && state.session?.guest && path !== "/api/login") {
      state.session = null;
      location.assign("/connexion");
    }
  };
  function upload(path, files, report) {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", path);
      xhr.setRequestHeader("X-CSRFToken", csrf());
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) report(Math.round((100 * e.loaded) / e.total));
      };
      xhr.upload.onload = () => report(100);
      xhr.onload = () => {
        let result = {};
        try {
          result = JSON.parse(xhr.responseText);
        } catch {}
        if (xhr.status >= 200 && xhr.status < 300) resolve(result);
        else reject(Error(result.error || "L’envoi a échoué."));
      };
      xhr.onerror = () => reject(Error("Connexion interrompue. Les fichiers restent sélectionnés."));
      xhr.send(form);
    });
  }
  function header() {
    const signedIn = Boolean(state.session?.guest);
    const reference = signedIn && location.hash.split("?")[0] === "#/referentiel";
    const spaceLink = $("#nav-space"), refLink = $("#nav-reference");
    refLink.hidden = !signedIn;
    $("#mast .logout-button").hidden = !signedIn;
    (reference ? spaceLink : refLink).removeAttribute("aria-current");
    (reference ? refLink : spaceLink).setAttribute("aria-current", "page");
  }
  function go(hash) {
    if (location.pathname !== "/espace") {
      location.assign("/espace" + hash);
      return;
    }
    if (location.hash === hash) window.HPA.route();
    else location.hash = hash;
  }
  function meter(value, total) {
    return `<progress max="${total || 1}" value="${value}" aria-label="Critères renseignés">${value} / ${total}</progress>`;
  }
  Object.assign(HPA, { upload, header, go, meter,
    photoCredit: '<a class="credit" href="https://fr.pinterest.com/pin/1098878377851832416/" target="_blank" rel="noopener noreferrer">Image · BusterTravel</a>',
  });
})();
