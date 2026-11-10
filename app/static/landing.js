const accessForm = document.querySelector(".request-panel form");
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
