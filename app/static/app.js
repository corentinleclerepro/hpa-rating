(function () {
  "use strict";
  const {
    state,
    main,
    $,
    api,
    upload,
    render,
    header,
    loading,
    showErr,
    busy,
    dialog,
    close,
    go,
    esc,
    toast,
    workspace: W,
    access: A,
  } = HPA;
  const v = W.view;
  async function referenceData() {
    if (state.meta && state.ref) return;
    [state.meta, state.ref] = await Promise.all([api("/api/meta"), api("/api/referentiel")]);
  }
  async function dossier(id, step, cid, serial, stars) {
    const root = "/api/audits/" + id;
    const d = await api(root);
    if (serial !== state.screen) return;
    const flow = d.audit.workflow, originalStep = step, originalCid = cid;
    let notice = "";
    if (step !== "overview" && !flow.open_steps.includes(step)) {
      notice = HPA.guide.waiting(flow);
      step = flow.current;
      cid = flow.next_id;
    }
    const selected = step === "summary" && stars ? `?stars=${stars}` : "";
    const [criteria, score] = await Promise.all([
      api(root + "/criteria" + selected),
      api(root + "/score" + selected),
    ]);
    if (serial !== state.screen) return;
    const sheet = step === "prerequisites" || step === "criteria";
    if (sheet) {
      const group = criteria.criteria.filter(c => c.code !== "NA" && HPA.guide.stepOf(c) === step && flow.allowed_ids.includes(c.id));
      if (!group.some(c => c.id === cid)) {
        if (cid) notice = "Ce numéro n’est pas ouvert dans cette étape. " + (flow.next_id ? HPA.guide.waiting(flow) : "");
        cid = (step === flow.current && flow.next_id) || group.find(c => c.id === d.audit.resume_criterion)?.id || group[0]?.id || null;
      }
    } else cid = null;
    if (step !== originalStep || cid !== originalCid)
      window.history.replaceState(null, "", `#/dossier/${id}/${step}${cid ? "/" + cid : ""}`);
    const moved = id !== v.audit?.id || step !== v.step || cid !== v.cid;
    if (id !== v.audit?.id || step !== v.step) {
      v.search = "";
      v.filter = "";
      v.ajo = false;
    }
    Object.assign(v, {
      audit: d.audit,
      evidences: d.evidences,
      history: d.history,
      criteria: criteria.criteria,
      score: score.score,
      reachable: score.reachable,
      stars: score.stars,
      step,
      cid: cid || null,
    });
    if (cid) {
      const current = v.criteria.find((c) => c.id === cid);
      if (current && current.code !== "NA" && ["criteria", "prerequisites"].includes(step)) {
        if (v.audit.resume_criterion !== cid) {
          await api(root + "/resume", "PUT", { criterion_id: cid, stars: v.stars });
          if (serial !== state.screen) return;
          v.audit.resume_criterion = cid;
        }
      } else v.cid = null;
    }
    W.draw();
    if (moved) window.scrollTo({top:0, behavior:"instant"});
    if (notice) toast(notice);
  }
  async function route(opts = {}) {
    const index = ++state.screen;
    try {
      if (!state.session) state.session = await api("/api/session");
      if (index !== state.screen) return;
      header();
      if (!state.session.guest) {
        A.guest();
        return;
      }
      if (!opts.quiet) loading();
      await referenceData();
      if (index !== state.screen) return;
      const parts = location.hash.split("?")[0].replace(/^#\/?/, "").split("/");
      if (parts[0] === "referentiel") {
        HPA.renderReference();
        return;
      }
      if (parts[0] === "dossier" && /^[a-f0-9]{12}$/.test(parts[1] || "")) {
        const step = W.steps.some((x) => x[0] === parts[2]) ? parts[2] : "overview";
        await dossier(parts[1], step, /^\d+$/.test(parts[3] || "") ? parts[3] : null, index, opts.stars);
      } else {
        const [{ audits }, { attached }] = await Promise.all([api("/api/audits"),api("/api/audits/brouillon")]);
        if (index === state.screen) W.list(audits,attached);
      }
    } catch (e) {
      if (index === state.screen) showErr(e);
    }
  }
  HPA.route = route;
  function profileData(form) {
    const f = new FormData(form);
    const body = {
      name: f.get("name"),
      type: f.get("type"),
      mention: f.get("mention"),
      target_stars: Number(f.get("target_stars")),
    };
    if (form.id === "profile-form") {
      body.profile = {};
      for (const x of state.meta.profile_fields) {
        const value = f.get("pf_" + x.key);
        if (value !== "" && value !== null)
          body.profile[x.key] = x.type === "bool" ? value === "true" : Number(value);
      }
    }
    return body;
  }
  async function saveForm(form, submitter) {
    const button = submitter || form.querySelector("button:not([type=button])");
    const data = new FormData(form),
      cid = form.dataset.cid;
    const advancing = button?.value === "advance";
    const sibling = form.closest(".guided-sheet")?.querySelector(".criterion-form");
    const draft = sibling && sibling !== form ? Array.from(new FormData(sibling).entries()) : null;
    await busy(
      button,
      async () => {
        if (form.id === "create-audit") {
          const { audit } = await api("/api/audits", "POST", profileData(form));
          close();
          go(`#/dossier/${audit.id}/profile`);
          return;
        }
        if (form.id === "delete-audit") {
          await api("/api/audits/" + form.dataset.id, "DELETE", { confirm_name: data.get("confirm_name") });
          close();
          go("#/");
          toast("Dossier supprimé.");
          return;
        }
        if (form.id === "clone-audit") {
          const { audit } = await api(W.base() + "/clone", "POST", { name: data.get("name") });
          close();
          go(`#/dossier/${audit.id}`);
          return;
        }
        if (form.id === "remove-proof-form") {
          await api("/api/evidence/" + form.dataset.id, "DELETE");
          close();
        } else if (form.id === "profile-form") {
          const {audit} = await api(W.base(), "PATCH", {...profileData(form), confirm_profile:advancing});
          if (advancing) {
            toast("Profil confirmé.");
            go(HPA.guide.entry(audit.workflow, W.link));
            return;
          }
        } else if (form.id === "proof-review") {
          await api(W.base() + "/review-proofs","POST",{reviewed:data.has("reviewed")});
          toast("Revue des justificatifs enregistrée.");
          go(W.link("summary"));
          return;
        } else if (form.matches(".criterion-form")) {
          const {workflow} = await api(`${W.base()}/items/${cid}`, "PUT", {
            status: data.get("status"),
            validated_by: data.get("validated_by"),
            notes: data.get("notes"),
            awarded_points: Number(data.get("awarded_points")) || null,
            stars: v.audit.target_stars,
            advance: advancing,
          });
          if (advancing) {
            toast(`Critère ${cid} enregistré.`);
            go(HPA.guide.entry(workflow, W.link));
            return;
          }
        } else if (form.matches(".upload-form")) {
          const meter = form.querySelector("progress"),
            msg = form.querySelector("[data-feedback]");
          meter.hidden = false;
          meter.value = 0;
          msg.textContent = "Envoi en cours…";
          await upload(`${W.base()}/items/${cid}/evidence`, Array.from(form.elements.files.files), (n) => {
            meter.value = n;
            msg.textContent = n === 100 ? "Fichiers envoyés. Enregistrement…" : `Envoi · ${n} %`;
          });
        } else if (form.matches(".url-form"))
          await api(`${W.base()}/items/${cid}/evidence/url`, "POST", { url: data.get("url") });
        else if (form.matches(".caption-form"))
          await api("/api/evidence/" + form.dataset.id, "PATCH", { caption: data.get("caption") });
        await route({ quiet: true });
        if (draft && v.cid === sibling.dataset.cid) {
          const restored = document.querySelector(".guided-sheet .criterion-form");
          for (const [key, value] of draft) if (restored?.elements.namedItem(key)) restored.elements.namedItem(key).value = value;
        }
        toast("Enregistré.");
      },
      form.matches(".upload-form") ? "Envoi en cours…" : "Enregistrement…",
    );
  }
  document.addEventListener("submit", (e) => {
    const form = e.target;
    e.preventDefault();
    if (form.id === "guest-login") {
      A.submit(form);
      return;
    }
    saveForm(form, e.submitter);
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.criterion) {
        const cid = b.dataset.criterion;
        if (v.cid === cid) go(W.link(v.step));
        else go(W.link(v.step, cid));
        return;
      }
      if (b.dataset.stars) {
        await route({ quiet: true, stars: Number(b.dataset.stars) });
        return;
      }
      if (b.dataset.delete) {
        const a = v.list.find((row) => row.id === b.dataset.delete);
        dialog(
          `<h2>Supprimer ce dossier ?</h2><p>Les critères, les justificatifs et le fil chronologique seront effacés définitivement.</p><form id="delete-audit" data-id="${a.id}"><label>Retapez le nom exact <strong>${esc(a.name)}</strong><input required autocomplete="off" name="confirm_name"></label><button class="destructive">Supprimer définitivement</button><p data-feedback role="status"></p></form>`,
        );
        return;
      }
      if (b.dataset.removeProof) {
        dialog(
          `<h2>Retirer ce justificatif ?</h2><p>Un critère qui exige une pièce repassera à « Preuve manquante » si vous retirez la dernière.</p><form id="remove-proof-form" data-id="${b.dataset.removeProof}"><button class="destructive">Retirer la pièce</button><p data-feedback role="status"></p></form>`,
        );
        return;
      }
      if (b.dataset.stale) {
        await busy(b, async () => {
          await api("/api/evidence/" + b.dataset.stale, "PATCH", { stale: Number(b.dataset.value) });
          await route({ quiet: true });
          toast("Justificatif mis à jour.");
        });
        return;
      }
      switch (b.dataset.act) {
        case "back-to-top":
          main.focus({ preventScroll: true });
          window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
          break;
        case "claim-draft":
          await busy(b, async () => {
            const draft = HpaDraft.read(), source = b.dataset.source;
            if (source === "local" && (!draft?.ready || draft.id !== b.dataset.draft)) {
              throw new Error("Le brouillon de cet appareil a changé. Rechargez votre espace.");
            }
            const body = source === "local" ? {source, draft:HpaDraft.packet(draft)} : {source, id:b.dataset.draft};
            const result = await api("/api/audits/brouillon","POST",body);
            HpaDraft.erase(result.draft_id);
            const {audit} = await api("/api/audits/" + result.id);
            go(HPA.guide.entry(audit.workflow, (step,cid) =>
              "#/dossier/" + result.id + "/" + step + (cid ? "/" + cid : "")));
          }, "Reprise du brouillon…");
          break;
        case "retry":
          await route();
          break;
        case "close":
          close();
          break;
        case "create":
          W.create();
          break;
        case "clone":
          dialog(
            `<h2>Dupliquer le dossier</h2><p>Les justificatifs copiés seront marqués « à rafraîchir ».</p><form id="clone-audit"><label>Nom de la copie<input name="name" value="${esc(v.audit.name)} — copie" maxlength="180" required></label><button>Créer la copie</button><p data-feedback role="status"></p></form>`,
          );
          break;
        case "sample":
          await busy(
            b,
            async () => {
              const { audit } = await api("/api/audits/demo", "POST", {});
              go(`#/dossier/${audit.id}`);
            },
            "Création de l’exemple…",
          );
          break;
        case "logout":
          await HPA.signOut(b, "/api/logout/guest", "/connexion");
          break;
      }
    } catch (err) {
      toast(err.message);
    }
  });
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (el.id === "criterion-search") v.search = el.value;
    else if (el.id === "criterion-filter") v.filter = el.value;
    else if (el.id === "ajo-filter") v.ajo = el.checked;
    else return;
    const list = $("#criterion-list");
    if (list) list.innerHTML = W.rows();
  });
  window.addEventListener("hashchange", () => route());
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) {
      state.session = null;
      route();
    }
  });
  route();
})();
