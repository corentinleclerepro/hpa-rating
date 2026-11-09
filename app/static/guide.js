(function () {
  "use strict";
  const { esc } = HPA;
  const steps = [
    ["profile", "Profil"], ["prerequisites", "Prérequis"], ["criteria", "Critères"],
    ["proofs", "Justificatifs"], ["summary", "Synthèse et export"],
  ];
  const help = {
    journey: ["Comment fonctionne le parcours ?", "Suivez les étapes numérotées. Dans les prérequis et les critères, ouvrez la fiche proposée, consignez votre constat, puis choisissez « Enregistrer et continuer ».",
      "Le prochain numéro applicable s’ouvre. Les numéros qui ne concernent pas votre établissement sont sautés. Vous pouvez corriger une réponse antérieure ; vos autres réponses sont conservées."],
    profile: ["Décrire mon établissement", "Vérifiez le type, la mention et les étoiles visées. Indiquez le nombre total d’emplacements, précisez les équipements connus, puis confirmez le profil.",
      "Ces réponses déterminent les critères à examiner. Si vous changez le profil plus tard, le guide recalcule leur ordre et vous ramène au premier point à traiter."],
    prerequisites: ["Renseigner un prérequis", "Lisez la condition, vérifiez-la pour votre établissement et choisissez le statut qui décrit la situation. Une note peut préciser ce qui reste à vérifier.",
      "Enregistrer votre constat ouvre le prochain numéro applicable. Un prérequis non satisfait reste signalé dans la synthèse et peut empêcher le classement."],
    criteria: ["Renseigner un critère", "Comparez vos équipements ou pratiques à l’exigence affichée pour votre catégorie. Choisissez un statut, ajoutez si utile une note ou une pièce, puis enregistrez.",
      "Chaque critère applicable est présenté dans l’ordre du référentiel. Renseigner un critère fait avancer le parcours ; seuls les éléments validés peuvent rapporter des points."],
    status: ["Quel statut choisir ?", "« En cours » : la vérification a commencé. « Preuve manquante » : un document est attendu. « Non conforme » : l’exigence n’est pas remplie. « Validé » : vous avez vérifié qu’elle est remplie.",
      "Ces quatre statuts permettent d’avancer. « À traiter » garde le critère en attente. Vous pouvez enregistrer vos notes en brouillon et reprendre ici plus tard."],
    evidence: ["Joindre un justificatif", "Sur la fiche du critère, choisissez un PDF ou une photo puis cliquez sur « Envoyer les fichiers ». Pour une preuve en ligne, collez son adresse dans « Ajouter un lien ».",
      "La pièce reste rattachée à ce numéro et apparaît dans le dossier exporté. Quand un justificatif est obligatoire, il faut au moins une preuve pour choisir « Validé »."],
    proofs: ["Relire les justificatifs", "Ouvrez les fichiers et les liens, vérifiez qu’ils correspondent au bon critère et repérez les pièces à rafraîchir. Revenez sur la fiche concernée pour corriger un élément.",
      "Confirmer la revue ouvre la synthèse, même si des pièces manquent. La confirmation ne rend aucun critère conforme. Modifier ensuite un constat ou une pièce demande une nouvelle revue."],
    summary: ["Lire et exporter la synthèse", "Consultez les points obligatoires, les points à la carte et les blocages. Choisissez le ZIP pour les pièces ou la synthèse à imprimer pour le bilan.",
      "Le résultat dépend des constats enregistrés. Simuler une autre catégorie ne change ni les étoiles visées, ni les réponses, ni la progression du dossier."],
  };
  const lock = '<svg class="guide-lock" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="3.8" y="7" width="8.4" height="6.5" rx="1.5"/><path d="M5.6 7V5a2.4 2.4 0 0 1 4.8 0v2"/></svg>';
  const question = (key) => `<button type="button" class="guide-help" data-guide-help="${key}" aria-label="Aide : ${esc(help[key][0])}" aria-haspopup="dialog"><span aria-hidden="true">?</span></button>`;
  const criterionQuestion = (c) => `<button type="button" class="guide-help" data-guide-help="criterion" data-help-cid="${esc(c.id)}" aria-label="Aide : comment renseigner le critère ${esc(c.id)} ?" aria-haspopup="dialog"><span aria-hidden="true">?</span></button>`;
  function criterionHelp(c, dossier) {
    if (!c) return null;
    const examples = {
      "1": "Vérifiez la capacité d’accueil et le nombre d’emplacements à partir des documents de votre établissement. Comparez-les à la condition affichée sur la fiche.",
      "2": "Prenez le permis d’aménager. Comparez le nombre autorisé au nombre réellement exploité et à celui de votre demande. Notez les chiffres relevés et joignez le document à cette fiche.",
      "4": "Faites le trajet qu’un client suit depuis l’entrée jusqu’à son emplacement. Regardez l’enseigne et les panneaux : sont-ils propres, lisibles et en bon état ? Notez ce qui doit être nettoyé ou remplacé.",
      "17": "Parcourez quelques emplacements avec votre plan. Vérifiez que leur identification sur le terrain correspond au plan et joignez une pièce qui montre ce repérage.",
      "21": "Reprenez votre relevé de surfaces et le nombre d’emplacements concernés. Comparez la superficie moyenne à l’exigence affichée pour votre catégorie et conservez le relevé sur la fiche.",
    };
    const example = dossier.reference_version === "atout-france-2019-195" && examples[c.id];
    const how = example || (c.exigence ? `Vérifiez sur place l’exigence en ${dossier.target_stars} étoiles : « ${c.exigence} ». Notez votre mesure ou votre constat.` :
      `Vérifiez ce point dans votre établissement : « ${c.title} ». Notez le résultat et, en cas d’écart, l’action à prévoir.`);
    const type = ({X:"obligatoire",O:"à la carte",ONC:"obligatoire non compensable"})[c.code];
    const rule = c.code === "PRQ" ? "C’est un prérequis : il ne rapporte pas de points mais son résultat compte pour l’éligibilité." :
      `Ce critère ${type || c.code} vaut ${c.points_min ? "jusqu’à " : ""}${c.points} point${c.points > 1 ? "s" : ""} dans la catégorie visée.`;
    return [`Renseigner le critère n° ${c.id}`, how, rule + (c.ajo ? " Une pièce est nécessaire pour le déclarer validé." : "") + " Un constat non conforme permet aussi de poursuivre."];
  }
  const index = (key) => steps.findIndex(s => s[0] === key);
  const label = (key) => steps[index(key)]?.[1] || "";
  const stepOf = (criterion) => criterion.chapter === 0 ? "prerequisites" : "criteria";
  const entry = (flow, link) => link(flow.current, flow.next_id || "");
  function waiting(flow) {
    if (flow.next_id) return `Renseignez d’abord le critère ${flow.next_id}.`;
    if (flow.current === "profile") return "Confirmez d’abord le profil.";
    return "Confirmez d’abord la revue des justificatifs.";
  }
  function nav(flow, step, link) {
    return `<nav class="journey-nav" aria-label="Étapes du dossier"><div class="journey-top"><strong>Votre parcours ${question("journey")}</strong><span>Étape ${flow.number} sur 5</span></div><ol>${steps.map(([key, title], i) => {
      const opened = flow.open_steps.includes(key), done = i < flow.number - 1;
      const contents = `<b aria-hidden="true">${done ? "✓" : i+1}</b><span>${esc(title)}</span>`;
      return `<li>${opened ? `<a href="${link(key)}" class="${done ? "passed" : "active"}" ${step === key || (step === "overview" && key === flow.current) ? 'aria-current="step"' : ""} aria-label="Étape ${i+1} : ${esc(title)}${done ? ', déjà parcourue' : ', en cours'}">${contents}</a>` : `<span class="not-open" aria-disabled="true" aria-label="Étape ${i+1} : ${esc(title)}, verrouillée">${contents}${lock}</span>`}</li>`;
    }).join("")}</ol></nav>`;
  }
  const modal = document.getElementById("guide-help-dialog");
  let trigger = null;
  document.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-guide-help]");
    if (btn) {
      const v = HPA.workspace?.view;
      const text = btn.dataset.guideHelp === "criterion" && v?.audit ?
        criterionHelp(v.criteria.find(c=>c.id === btn.dataset.helpCid),v.audit) : help[btn.dataset.guideHelp];
      if (!text) return;
      trigger = btn;
      modal.innerHTML = `<div class="eyebrow"><i></i>Aide au parcours</div><h2 id="guide-help-title">${esc(text[0])}</h2><h3>Comment faire</h3><p>${esc(text[1])}</p><h3>Ce que ça change</h3><p>${esc(text[2])}</p><button type="button" data-close-guide autofocus>Compris</button>`;
      modal.showModal();
    } else if (event.target.closest("[data-close-guide]") || event.target === modal) modal.close();
  });
  modal.addEventListener("close", () => { if (trigger?.isConnected) trigger.focus({preventScroll:true}); trigger = null; });
  HPA.guide = { steps, label, stepOf, entry, nav, lock, question, criterionQuestion, waiting };
})();
