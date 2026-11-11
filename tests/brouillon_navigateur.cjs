const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const {chromium} = require(process.env.HPA_PLAYWRIGHT_CORE || "playwright-core");
const test = JSON.parse(readFileSync(0, "utf8"));
const mobileSize = {width:390,height:844}, desktopSize = {width:1280,height:800};
const outputs = process.env.HPA_QA_OUTPUT;

async function checkStack(page, width) {
  await page.setViewportSize(width === 390 ? mobileSize : desktopSize);
  await page.goto(test.guest);
  await page.emulateMedia({reducedMotion:"no-preference"});
  const stack = page.locator(".steps");
  const positions = await stack.evaluate(async list => {
    const cards = [...list.children];
    const step = cards.at(-1).getBoundingClientRect().top + scrollY;
    const targetTop = parseFloat(getComputedStyle(cards.at(-1)).top);
    scrollTo({top:step-targetTop+18,behavior:"instant"});
    await new Promise(requestAnimationFrame);
    const rects = cards.map(card => card.getBoundingClientRect());
    const last = rects.at(-1);
    return {tops:rects.map(r=>Math.round(r.top)), targets:cards.map(card=>getComputedStyle(card).top),
      heights:rects.map(r=>Math.round(r.height)), bottom:list.getBoundingClientRect().bottom, firstBottom:rects[0].bottom,
      header:document.querySelector("header").getBoundingClientRect().bottom,
      topCard:document.elementFromPoint(last.left+last.width/2,last.top+10)?.closest("li")===cards.at(-1)};
  });
  assert.ok(positions.tops[0] >= positions.header-1 && positions.topCard,JSON.stringify(positions));
  assert.ok(positions.tops[4] < positions.firstBottom,JSON.stringify(positions));
  positions.tops.slice(1).forEach((top,i) => assert.ok(top > positions.tops[i] && top < positions.tops[i]+20,JSON.stringify(positions)));
  if (outputs && width === 1280) await page.screenshot({path:path.join(outputs,"Hpa-Rating-empilement.jpg")});
  await page.emulateMedia({reducedMotion:"reduce"});
  assert.equal(await stack.locator("li").first().evaluate(el=>getComputedStyle(el).position),"static");
  await page.emulateMedia({reducedMotion:"no-preference"});
  console.log("Empilement de cinq cartes, "+width+" px : "+positions.tops.join(", ")+" px. Mouvement réduit vérifié.");
}

async function answer(page, name) {
  await page.getByRole("radio",{name,exact:true}).check();
  await page.locator("#starter-sheet button").click();
}
async function enter(page, code) {
  await page.goto(test.guest+"/connexion");
  await page.getByLabel("Code personnel").fill(code);
  await page.locator("#guest-login button").click();
  await page.getByRole("heading",{name:"Mes dossiers",exact:true}).waitFor();
}
async function run() {
  let mobile;
  const desktop = await chromium.launch({channel:process.env.HPA_BROWSER_B || "msedge", headless:true});
  const launchMobile = () => chromium.launchPersistentContext(test.profile,{
    channel:process.env.HPA_BROWSER_A || "chrome",headless:true,viewport:mobileSize});
  try {
    mobile = await launchMobile();
    let p = await mobile.newPage();
    await checkStack(p,390);
    const desk = await desktop.newContext({viewport:desktopSize}), guest = await desk.newPage();
    await checkStack(guest,1280);
    await p.goto(test.guest);
    await p.getByRole("link",{name:"Commencer mon dossier gratuitement"}).click();
    await p.getByLabel("Nombre total d’emplacements").fill("62");
    await p.locator("#starter-profile button").click();
    await answer(p,"En cours");
    await p.getByRole("heading",{name:"Permis d’aménager et emplacements"}).waitFor();
    await mobile.close();
    mobile = await launchMobile();
    p = await mobile.newPage();
    await p.goto(test.guest);
    await p.getByRole("link",{name:"Reprendre mon dossier"}).click();
    await p.getByRole("heading",{name:"Permis d’aménager et emplacements"}).waitFor();
    assert.equal(await p.locator("#draft-progress").innerText(),"1 sur 3 fiches renseignées");
    await answer(p,"Preuve manquante");
    await answer(p,"Validé");
    await p.getByRole("link",{name:"Demander un accès gratuit pour continuer"}).click();
    await p.getByLabel("Nom du camping").fill("Camping fictif de la Pinède");
    await p.getByLabel("Adresse e-mail").fill("parcours@example.invalid");
    const attach = p.getByRole("checkbox",{name:/Joindre mon brouillon/});
    assert.equal(await attach.isChecked(),false);
    await attach.check();
    await p.route("**/demande-acces", route=>route.abort(),{times:1});
    await p.locator("#starter-request button").click();
    await p.getByText(/L’envoi a été interrompu/).waitFor();
    assert.equal(await p.getByLabel("Adresse e-mail").inputValue(),"parcours@example.invalid");
    await p.getByRole("button",{name:"Réessayer l’envoi"}).click();
    await p.getByRole("heading",{name:"Demande reçue"}).waitFor();
    console.log("Chrome fermé et relancé : profil et première fiche retrouvés. Demande jointe après nouvel essai.");

    const staff = await desktop.newContext(), admin = await staff.newPage();
    await admin.goto(test.admin);
    await admin.locator("#admin-login [name=password]").fill(test.password);
    await admin.locator("#admin-login [name=otp]").fill(test.recovery);
    await admin.locator("#admin-login button").click();
    await admin.getByRole("button",{name:"Accepter et créer un code"}).click();
    await admin.locator("#invitation-text").waitFor();
    const match = (await admin.locator("#invitation-text").inputValue()).match(/HPA-(?:[A-Z2-7]{4}-){5}[A-Z2-7]{4}/);
    assert.ok(match,"Invitation de l’établissement fictif");
    await guest.goto(test.guest);
    assert.equal(await guest.getByRole("link",{name:"Reprendre mon dossier"}).count(),0);
    await enter(guest,match[0]);
    await guest.getByRole("button",{name:"Reprendre mon brouillon"}).click();
    await guest.waitForURL(/dossier\/[a-f0-9]+\/criteria\/5$/);
    await guest.locator(".criterion-form select[name=status]").selectOption("IN_PROGRESS");
    await guest.locator(".criterion-form button[value=advance]").click();
    await guest.waitForURL(/\/criteria\/6$/);
    console.log("Edge indépendant : code accepté, reprise au critère 5 puis avancement au 6.");

    await admin.reload();
    const stats = admin.getByRole("region",{name:"Suivi du mini-dossier"});
    await stats.locator("dd").first().waitFor();
    const totals = (await stats.locator("dd").allTextContents()).map(Number);
    assert.ok(totals[0]>=1); assert.deepEqual(totals.slice(1),[1,1,1]);
    if (outputs) await stats.screenshot({path:path.join(outputs,"Hpa-Rating-suivi-mini-dossier.jpg")});
    await enter(p,match[0]);
    await p.getByRole("button",{name:"Reprendre mon brouillon"}).click();
    await p.waitForURL(/\/criteria\/6$/);
    await p.goto(test.guest+"/espace");
    await p.getByRole("heading",{name:"Mes dossiers",exact:true}).waitFor();
    assert.equal(await p.locator(".dossiercard").count(),1);
    console.log("Retour sur Chrome : un seul dossier, réponses conservées. Compteurs vérifiés :",totals.join(", "));
  } finally {
    if (mobile) await mobile.close();
    await desktop.close();
  }
}
run().catch(err => { console.error(err.message); process.exitCode=1; });
