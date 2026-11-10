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
  const transfers = new WeakMap();
  function sendPart(path, data, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", path);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.setRequestHeader("X-CSRFToken", csrf());
      xhr.upload.onprogress = e => onProgress(e.loaded);
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) return resolve();
        let message = "Échec de l’envoi. Réessayez.";
        try { message = JSON.parse(xhr.responseText).error || message; } catch {}
        const error = new Error(message);
        error.status = xhr.status;
        reject(error);
      };
      xhr.onerror = () => reject(new Error("Connexion interrompue. Les fichiers restent sélectionnés."));
      xhr.send(data);
    });
  }
  async function uploadParts(path, files, report) {
    if (!files.length) throw new Error("Sélectionnez un fichier.");
    const root = path + "/transfers";
    const total = files.reduce((n, file) => n + file.size, 0);
    let transfer = transfers.get(files[0]);
    if (!transfer || transfer.path !== path || Date.now()-transfer.time > 50*60*1000 ||
        transfer.files.length !== files.length || !files.every((file,i) => file===transfer.files[i])) {
      const ticket = await HPA.api(root, "POST", {files:files.map(f => ({name:f.name,size:f.size}))});
      transfer = {path, files, ticket, time:Date.now(), offsets:files.map(() => 0)};
      transfers.set(files[0], transfer);
    }
    const chunk = transfer.ticket.chunk_bytes;
    let done = transfer.offsets.reduce((sum, size) => sum+size, 0);
    try {
      for (let i=0; i<files.length; i++) {
        for (let start=transfer.offsets[i]; start<files[i].size; start+=chunk) {
          const data = files[i].slice(start, start+chunk);
          await sendPart(root+"/"+transfer.ticket.files[i]+"/"+Math.floor(start/chunk), data,
            n => report(Math.min(99, Math.floor(100*(done+n)/total))));
          done += data.size;
          transfer.offsets[i] += data.size;
        }
      }
      const result = await HPA.api(root+"/complete","POST",{files:transfer.ticket.files});
      transfers.delete(files[0]);
      report(100);
      return result;
    } catch (err) {
      if (err.status===404) transfers.delete(files[0]);
      throw err;
    }
  }
  function upload(path, files, report) {
    if (state.meta?.chunked_upload) return uploadParts(path, files, report);
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
