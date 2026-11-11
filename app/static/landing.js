const accessForm = document.querySelector(".request-panel form");
function updateStarterLink() {
  const label = document.getElementById("start-label");
  if (label) label.textContent = HpaDraft.read() ? "Reprendre mon dossier" : "Commencer mon dossier gratuitement";
}
updateStarterLink();
window.addEventListener("pageshow", updateStarterLink);
window.addEventListener("storage", updateStarterLink);
if (location.pathname === "/" && accessForm && !accessForm.querySelector('[role="alert"]')) {
  const countHome = () => {
    if (document.visibilityState !== "visible") return;
    document.removeEventListener("visibilitychange",countHome);
    HpaDraft.count("home",accessForm.elements.csrfmiddlewaretoken.value);
  };
  document.addEventListener("visibilitychange",countHome); countHome();
}
const submitButton = accessForm?.querySelector("button");
accessForm?.addEventListener("submit", () => {
  submitButton.disabled = true;
  submitButton.textContent = "Envoi en cours…";
});
window.addEventListener("pageshow", event => {
  if (event.persisted && submitButton) {
    submitButton.disabled = false;
    submitButton.textContent = "Envoyer ma demande →";
  }
});
