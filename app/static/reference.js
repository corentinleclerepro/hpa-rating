(function () {
  "use strict";
  const { state, esc, render } = HPA;
  const categories = ["1", "2", "3", "4", "5"];
  const establishments = { camping: "Camping", prl: "Parc résidentiel de loisirs (PRL)" };
  const ruleNames = {
    X: "Obligatoire",
    ONC: "Obligatoire non compensable",
    O: "À la carte",
    PRQ: "Prérequis",
    NA: "Non applicable",
  };
  const allFilters = { q: "", chapitre: "", rubrique: "", type: "", etoiles: "", regle: "", ajo: false };

  function normalize(value) {
    return String(value || "").toLocaleLowerCase("fr")
      .normalize("NFD").replace(/\p{M}/gu, "")
      .replace(/œ/g, "oe").replace(/æ/g, "ae")
      .replace(/n[º°]/g, "n ")
      .replace(/\bwi[\s‐‑–—-]*fi\b/g, "wifi")
      .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  }

  function parseQuery(input) {
    const text = normalize(input);
    // A number entered on its own refers to the official criterion, including "n° 17".
    const exact = /^(?:(?:critere\s*)?(?:(?:numero|no|n)\s*)?)(\d+)$/.exec(text);
    if (exact) return { id: String(Number(exact[1])), words: [] };
    return { id: null, words: text ? text.split(" ") : [] };
  }

  function sectionsOf(criteria, chapter) {
    const eligible = chapter === "" ? criteria : criteria.filter(c => String(c.chapter) === chapter);
    return [...new Set(eligible.map(c => c.section).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr"));
  }

  function readFilters(ref) {
    const query = location.hash.split("?").slice(1).join("?");
    const params = new URLSearchParams(query);
    const pick = (name, possible) => possible.includes(params.get(name)) ? params.get(name) : "";
    const chapitre = pick("chapitre", ref.chapters.map(chapter => String(chapter.id)));
    return {
      q: (params.get("q") || "").slice(0, 160),
      chapitre,
      rubrique: pick("rubrique", sectionsOf(ref.criteria, chapitre)),
      type: pick("type", Object.keys(establishments)),
      etoiles: pick("etoiles", categories),
      regle: pick("regle", Object.keys(ruleNames)),
      ajo: params.get("ajo") === "1",
    };
  }

  function saveFilters(filters) {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(filters)) {
      if (value) params.set(name, value === true ? "1" : value);
    }
    const query = params.toString();
    const hash = "#/referentiel" + (query ? "?" + query : "");
    if (location.hash !== hash) history.replaceState(history.state, "", hash);
  }

  function requiredProof(criterion, establishment) {
    return criterion.ajo || (criterion.ajo_prl && establishment !== "camping");
  }

  function ruleAt(criterion, stars) {
    return criterion.rules?.[stars] || criterion.rules?.["*"] || { code: "NA", points: 0 };
  }

  function indexCriterion(c) {
    return {
      criterion: c,
      text: normalize([c.id, c.title, c.section, c.precisions].join(" ")),
      requirements: Object.fromEntries(categories.map(n => [n, normalize(ruleAt(c, n).exigence)])),
    };
  }

  function matches(record, filters, query, stars) {
    const c = record.criterion;
    if (query.id !== null && String(c.id) !== query.id) return false;
    if (filters.chapitre !== "" && String(c.chapter) !== filters.chapitre) return false;
    if (filters.rubrique && c.section !== filters.rubrique) return false;
    if (filters.type && c.applies_to?.length && !c.applies_to.includes(filters.type)) return false;
    if (filters.ajo && !requiredProof(c, filters.type)) return false;
    // Text in a category-specific requirement and the rule filter must match the same category.
    return stars.some(n => {
      const code = ruleAt(c, n).code;
      if (filters.regle && code !== filters.regle) return false;
      if (filters.etoiles && !filters.regle && code === "NA") return false;
      return query.words.every(word => {
        if (word === "ajo") return requiredProof(c, filters.type);
        if (Object.hasOwn(ruleNames, word.toUpperCase())) return word.toUpperCase() === code;
        return record.text.includes(word) || record.requirements[n].includes(word);
      });
    });
  }

  function options(entries, placeholder, selected) {
    const entry = ([value, label]) =>
      `<option value="${esc(value)}"${String(value) === selected ? " selected" : ""}>${esc(label)}</option>`;
    return [["", placeholder], ...entries].map(entry).join("");
  }

  function selectField(name, label, entries, placeholder, selected) {
    return `<label class="ref-field" for="ref-${name}">${esc(label)}
      <select id="ref-${name}" name="${name}">${options(entries, placeholder, selected)}</select></label>`;
  }

  function toolbar(ref, f) {
    const chapters = ref.chapters.map(ch => [String(ch.id), ch.titre]);
    const sections = sectionsOf(ref.criteria, f.chapitre).map(s => [s, s]);
    const stars = categories.map(n => [n, n === "1" ? "1 étoile" : n + " étoiles"]);
    const rules = Object.entries(ruleNames).map(([code, name]) => [code, `${name} (${code})`]);
    return `<section class="ref-tools panel" role="search" aria-label="Rechercher et filtrer les critères">
      <div class="ref-primary">
        <label for="ref-q" class="ref-field ref-search">Rechercher un critère
          <span class="ref-search-box"><input id="ref-q" type="search" name="q" maxlength="160" autocomplete="off" placeholder="Numéro ou mot-clé, par exemple piscine" value="${esc(f.q)}"></span>
        </label>
        ${selectField("chapitre", "Chapitre", chapters, "Tous les chapitres", f.chapitre)}
        ${selectField("rubrique", "Rubrique", sections, "Toutes les rubriques", f.rubrique)}
      </div>
      <div class="ref-secondary">
        ${selectField("type", "Établissement", Object.entries(establishments), "Camping et PRL", f.type)}
        ${selectField("etoiles", "Catégorie", stars, "Toutes les étoiles", f.etoiles)}
        ${selectField("regle", "Type de critère", rules, "Tous les types", f.regle)}
        <label class="ref-ajo"><input name="ajo" type="checkbox" ${f.ajo ? "checked" : ""}> Justificatif obligatoire (AJO)</label>
      </div>
    </section>`;
  }

  function criterionDetails(c, stars, sourceUrl) {
    const requirements = [];
    for (const n of stars) {
      const value = ruleAt(c, n).exigence;
      if (!value) continue;
      const previous = requirements[requirements.length - 1];
      if (previous?.value === value) previous.stars.push(n);
      else requirements.push({ value, stars: [n] });
    }
    const thresholds = requirements.map(group => `<li><strong>${group.stars.join(", ")} ★</strong> · ${esc(group.value)}</li>`);
    const source = c.source_page && sourceUrl ?
      `<a class="textlink" target="_blank" rel="noopener noreferrer" href="${esc(sourceUrl)}#page=${Number(c.source_page)}">Tableau officiel, page ${Number(c.source_page)} ↗</a>` : "";
    return `<div class="ref-detail">${c.precisions ? `<p>${esc(c.precisions)}</p>` : ""}
      ${thresholds.length ? `<ul>${thresholds.join("")}</ul>` : ""}${source}</div>`;
  }

  function tableRow(c, stars, f, sourceUrl) {
    const type = c.applies_to?.length === 1 ? (c.applies_to[0] === "prl" ? "PRL" : "Camping") : "";
    const context = [c.section, type, requiredProof(c, f.type) ? (c.ajo ? "AJO" : "AJO en PRL") : ""].filter(Boolean);
    const cells = stars.map(n => {
      const rule = ruleAt(c, n);
      const code = rule.code;
      const points = stars.length === 1 && code !== "NA" && code !== "PRQ" ?
        `<span class="ref-points">${c.points_min ? "jusqu’à " : ""}${esc(rule.points)} pt${rule.points > 1 ? "s" : ""}</span>` : "";
      return `<td class="ref-rule"><span class="ref-star-mobile" aria-hidden="true">${n} ★</span>
        <abbr class="ref-code" data-code="${esc(code)}" title="${esc(ruleNames[code] || code)}">${esc(code)}</abbr>${points}</td>`;
    });
    return `<tr><th scope="row" class="ref-number"><span class="ref-star-mobile">N° </span>${esc(c.id)}</th>
      <td class="ref-name"><details><summary>${esc(c.title)}</summary>${criterionDetails(c, stars, sourceUrl)}</details>
        <small>${esc(context.join(" · "))}</small></td>${cells.join("")}</tr>`;
  }

  function renderReference() {
    const ref = state.ref;
    const records = ref.criteria.map(indexCriterion);
    let filters = readFilters(ref);
    render(`<div class="wrap ref-page">
      <header class="ref-heading"><div><h1>Référentiel</h1>${HPA.referenceNote(ref.publication)}</div>
        <a class="textlink" href="${esc(ref.meta.source_url)}" target="_blank" rel="noopener noreferrer">Ouvrir le tableau officiel ↗</a></header>
      ${toolbar(ref, filters)}
      <div class="ref-results-head"><div><strong id="ref-count" role="status" aria-live="polite" aria-atomic="true"></strong>
        <span id="ref-rule-scope" class="ref-rule-scope" hidden>Le type choisi s’applique dans au moins une catégorie.</span></div>
        <button class="textbtn" id="ref-reset" type="button">Réinitialiser les filtres</button></div>
      <div id="ref-results"></div></div>`);
    const page = document.querySelector(".ref-page");
    const controls = page.querySelector(".ref-tools");
    const queryField = controls.querySelector("#ref-q");
    const sectionField = controls.querySelector("#ref-rubrique");
    const counter = page.querySelector("#ref-count");
    const ruleScope = page.querySelector("#ref-rule-scope");
    const results = page.querySelector("#ref-results");
    const reset = page.querySelector("#ref-reset");

    function refreshSections() {
      const sections = sectionsOf(ref.criteria, filters.chapitre);
      if (!sections.includes(filters.rubrique)) filters.rubrique = "";
      sectionField.innerHTML = options(sections.map(s => [s, s]), "Toutes les rubriques", filters.rubrique);
    }

    function refreshResults() {
      const stars = filters.etoiles ? [filters.etoiles] : categories;
      const query = parseQuery(filters.q);
      const found = records.filter(record => matches(record, filters, query, stars));
      reset.disabled = !Object.values(filters).some(Boolean);
      ruleScope.hidden = !found.length || !filters.regle || !!filters.etoiles;
      const suffix = found.length > 1 ? "s" : "";
      counter.textContent = found.length + " critère" + suffix + (reset.disabled ? "" : " sur " + records.length);
      if (!found.length) {
        results.innerHTML = '<div class="panel ref-empty"><h2>Aucun critère trouvé</h2><p>Essayez un autre mot-clé ou retirez un filtre.</p></div>';
        return;
      }
      const headings = stars.map(n => `<th class="ref-rule" scope="col">${n} ★</th>`).join("");
      results.innerHTML = `<div class="ref-table-wrap"><table class="ref-table" aria-label="Critères de classement par catégorie">
        <thead><tr><th scope="col">N°</th><th scope="col">Critère</th>${headings}</tr></thead>
        <tbody>${found.map(({ criterion }) => tableRow(criterion, stars, filters, ref.meta.source_url)).join("")}</tbody>
      </table></div>`;
    }
    queryField.addEventListener("input", () => {
      filters.q = queryField.value;
      saveFilters(filters);
      refreshResults();
    });
    controls.addEventListener("change", event => {
      const field = event.target;
      if (field === queryField || !Object.hasOwn(allFilters, field.name)) return;
      filters[field.name] = field.type === "checkbox" ? field.checked : field.value;
      if (field.name === "chapitre") refreshSections();
      saveFilters(filters);
      refreshResults();
    });
    reset.addEventListener("click", () => {
      filters = { ...allFilters };
      for (const field of controls.querySelectorAll("input,select")) {
        if (field.type === "checkbox") field.checked = false;
        else field.value = "";
      }
      refreshSections();
      saveFilters(filters);
      refreshResults();
      queryField.focus();
    });
    refreshResults();
  }

  HPA.renderReference = renderReference;
})();
