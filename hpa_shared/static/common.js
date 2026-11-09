(function () {
  "use strict";
  const $ = (q, root = document) => root.querySelector(q);
  const main = $("#main");
  const state = { session: null };
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
    );
  const date = (iso) =>
    iso
      ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso))
      : "Jamais";
  const csrf = () =>
    document.cookie
      .split("; ")
      .find((entry) => entry.startsWith(document.documentElement.dataset.csrfCookie + "="))
      ?.split("=")
      .slice(1)
      .join("=") || "";
  async function api(path, method = "GET", value) {
    const headers = { Accept: "application/json" };
    if (method !== "GET") headers["X-CSRFToken"] = csrf();
    if (value !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: value === undefined ? undefined : JSON.stringify(value),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      state.onHttpError?.(res.status, path);
      throw Error(data.error || `La demande a échoué (${res.status}).`);
    }
    return data;
  }
  function toast(s) {
    const el = $("#notice");
    el.textContent = s;
    el.classList.add("shown");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("shown"), 4300);
  }
  async function signOut(button, endpoint, destination) {
    if (button.disabled) return;
    const label = button.querySelector("span");
    const initialLabel = label.textContent;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    label.textContent = "Déconnexion…";
    try {
      await api(endpoint, "POST", {});
      location.replace(destination);
    } catch {
      label.textContent = initialLabel;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.focus();
      toast("La déconnexion a échoué. Réessayez.");
    }
  }
  function render(html) {
    main.innerHTML = html;
    main.setAttribute("aria-busy", "false");
  }
  function loading() {
    main.setAttribute("aria-busy", "true");
    main.innerHTML =
      '<div class="wrap" role="status" aria-label="Chargement"><div class="skeleton short"></div><div class="skeleton"></div><div class="skeleton"></div></div>';
  }
  function showErr(e) {
    render(
      `<div class="wrap narrow panel"><h1>Impossible d’ouvrir cette page</h1><p>${esc(e.message)}</p><button data-act="retry">Réessayer</button></div>`,
    );
  }
  async function busy(button, task, label = "Enregistrement…") {
    if (!button || button.disabled) return;
    const previous = button.textContent;
    const scope = button.closest("form,.actionbox,dialog") || button.parentElement;
    let msg = scope.querySelector("[data-feedback]");
    if (!msg) {
      msg = document.createElement("p");
      msg.dataset.feedback = "";
      msg.setAttribute("role", "status");
      scope.append(msg);
    }
    msg.textContent = "";
    msg.className = "feedback";
    button.disabled = true;
    button.textContent = label;
    try {
      await task();
    } catch (e) {
      msg.textContent = e.message + " Réessayez.";
      msg.className = "feedback error";
      button.dataset.failed = "1";
    } finally {
      button.disabled = false;
      button.textContent = button.dataset.failed ? "Réessayer" : previous;
    }
  }
  function dialog(html) {
    const d = $("#modal");
    d.innerHTML = `<div class="modal-head"><button class="close" aria-label="Fermer" data-act="close">×</button></div>${html}`;
    if (!d.open) d.showModal();
  }
  function close() {
    const d = $("#modal");
    if (d.open) d.close();
    d.replaceChildren();
  }
  $("#modal").addEventListener("close", (event) => {
    if (!event.target.open) event.target.replaceChildren();
  });
  window.HPA = { $, main, state, esc, date, csrf, api, toast, signOut, render, loading, showErr, busy, dialog, close };
})();
