# Hpa Rating

**Camp Compagnon**

Espace privé sur invitation, utilisable en local ou sur un serveur HTTPS, pour préparer un dossier de
classement en étoiles (1★–5★) d'un terrain de camping / caravanage ou d'un PRL,
selon le tableau de classement officiel (arrêté du 10 avril 2019, annexe I).

## Fonctionnalités

La vitrine publique présente les cinq étapes et reçoit les demandes d’accès. Les campings déjà invités retrouvent leurs dossiers sur `/connexion`. Dans l’administration web séparée, l’opérateur accepte ou refuse les demandes, copie les invitations à envoyer et gère les codes actifs.

Chaque dossier suit cinq étapes obligatoires : **Profil → Prérequis → Critères → Justificatifs → Synthèse et export**. Confirmer le profil (au moins le nombre total d’emplacements) ouvre le premier numéro applicable. Les fiches sont renseignées une à une dans l’ordre du référentiel ; enregistrer un constat autre que « À traiter » ouvre la suivante, même si le constat est défavorable. Les critères non applicables sont sautés. Les boutons **?** expliquent la démarche et ses effets.

Il est possible de corriger une réponse antérieure. Remettre un critère « À traiter » ou modifier les données d’applicabilité recalcule le point de reprise sans effacer les réponses ni les pièces. La revue explicite des justificatifs ouvre la synthèse et les exports, sans déclarer un dossier éligible. La synthèse signale les blocages ; la simulation ne modifie pas le parcours.

- **Moteur de calcul réglementaire** (`app/scoring.py`, pur + testé) :
  - prérequis (PRQ) bloquants ;
  - critères obligatoires non compensables (ONC) : tout écart = non éligible ;
  - ≥ 95 % des points obligatoires (X) ; chaque point X perdu dans la marge de 5 %
    compensé par **3 points à la carte (O)** supplémentaires ;
  - seuil de points à la carte par catégorie : 5 / 10 / 20 / 30 / 40 % pour 1★–5★ ;
  - codes X / O / ONC / NA / PRQ / AJO par étoile, filtrages par profil
    (camping vs PRL, mention tourisme/loisirs, piscine, locatifs, nb emplacements…).
- **Dossiers** : création avec profil, statuts par critère
  (À traiter / En cours / Preuve manquante / Non conforme / Validé),
  notes internes, « validé par ».
- **Preuves par critère** : upload de photos/PDF (stockées sur disque, noms nettoyés),
  liens URL (captures site web…), légendes, marquage « à rafraîchir ».
  Les critères **AJO** exigent au moins une preuve avant validation.
- **Dashboard** : double jauge (X à 95 % avec marqueur, O requis vs obtenu),
  alertes bloquantes, **simulateur « what-if »** (basculer 1★–5★),
  étoiles atteignables.
- **Exports prêts à envoyer à l'organisme évaluateur** (accrédité COFRAC) :
  - **ZIP structuré** selon la numérotation officielle :
    `Dossier_X/Chapitre_1_Equipements/<Section>/Critere_42_.../C42_01_photo.jpg`
    + `00_Book_de_synthese.html` + `00_manifest.json` ;
  - **Book de synthèse HTML** imprimable en PDF (fiche identité, scores, détail
    critère par critère avec notes et preuves).
- **Clonage de dossier** (renouvellement tous les 5 ans) : preuves copiées et
  marquées « à rafraîchir ».

## Hébergement HTTPS

L’installation Vercel utilise deux projets HTTPS distincts pour les campings et l’administration. L’administration protège ses sessions par mot de passe et second facteur. Les dossiers et les pièces sont conservés sur PostgreSQL pour permettre la reprise du travail. [Configuration Vercel et Supabase](deploy/supabase/README.md)

Le [guide de déploiement sur une VM](deploy/README.md) décrit la mise en service de `hpa-rating.campcompagnon.fr`, la vérification du certificat et les sauvegardes. Seul l’espace invité est publié. L’administration s’ouvre par un tunnel SSH et possède son propre stockage ; elle partage uniquement le registre d’invitations avec l’espace invité.

## Lancement sur localhost

L’espace invité et la console d’administration sont deux applications indépendantes. Elles peuvent être démarrées et arrêtées séparément. Avec Python 3.10+ sous Windows, installer les dépendances une fois :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

1. **Espace invité** : lancer `.venv\Scripts\python run.py`, puis ouvrir [Mes dossiers](http://localhost:8000/espace). Seul ce service ouvre les dossiers, pièces, synthèses et exports.
2. **Console privée** : dans un autre terminal, lancer `.venv\Scripts\python run_admin.py`, puis ouvrir [la console](http://127.0.0.1:8001/). Aucun lien vers elle ne figure dans l’espace invité. L’ancienne adresse sur le port 8000 ne sert plus de page.
3. **Première configuration uniquement** : si l’administrateur n’a pas encore de mot de passe, lancer `.venv\Scripts\python run_admin.py --setup-key ..\configuration-hpa.txt`. La fiche est privée, valable 24 heures et doit avoir un nouveau nom. Saisir la clé dans la console, choisir un mot de passe, associer l’application d’authentification, puis conserver les huit codes de secours. Un administrateur déjà configuré garde son mot de passe et son second facteur.

Dans la console, générer un code puis copier l’invitation pour l’envoyer soi-même. Le lien copié pointe sur **l’espace invité** ; pour un port personnalisé, configurer `HPA_GUEST_ORIGIN` avant de lancer la console. La révocation et le remplacement d’un code invalident les sessions correspondantes. Ils ne suppriment aucun dossier.

Pour rattacher d’anciens dossiers sans propriétaire à un accès d’essai, la distribution complète comprend la commande locale facultative `.venv\Scripts\python init_local.py ..\acces-essai.txt`. Elle ne tourne dans aucun des deux serveurs. Les dossiers déjà rattachés conservent leur propriétaire.

SQLite et les pièces restent dans le répertoire privé `data/`. Lors d’une installation dans deux répertoires différents, définir `HPA_DATA_DIR` sur le même chemin absolu pour les deux processus. Le registre des invitations garde les mêmes identifiants et empreintes. Les sessions invitées sont stockées dans `guest-sessions.sqlite3` ; le compte opérateur et ses sessions restent dans `access.sqlite3`, avec un autre cookie et une autre clé de signature. Lors du passage à cette version, les sessions invitées valides sont reprises sans les informations d’administration. Les deux serveurs écoutent uniquement en local ; fermer la console n’empêche pas un invité de travailler.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Installer `requirements-production.txt` pour inclure le test des deux serveurs de production et de leurs volumes séparés. Après le déploiement, `python deploy/verify.py https://hpa-rating.campcompagnon.fr` contrôle l’entrée publique sans invitation réelle.

## Référentiel

`data/referentiel.json` contient les 195 lignes numérotées du tableau Camping et PRL, avec les cinq catégories, les points, les seuils chiffrés, les précisions et la page source. Les valeurs ont été recoupées avec l’annexe I de l’arrêté du 10 avril 2019. Le critère 132 porte la mention AJO dans l’annexe. L’application demande donc une pièce pour ce critère. [Tableau Atout France](https://www.atout-france.fr/sites/default/files/2025-12/R%C3%A9f%C3%A9rentiel%20de%20classement%20-%20Camping%20%26%20PRL.pdf) · [Annexe I sur Légifrance](https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000038365246)

Les données du profil déterminent les exclusions. Les exigences qualitatives et les quantités d’équipement doivent être vérifiées sur place avant de valider. Les critères 22, 24, 115 et 131 permettent de saisir de 1 à 5 points. La simulation demande une nouvelle validation lorsqu’une catégorie supérieure impose un seuil différent.

Les anciens dossiers contenant des statuts ou des pièces restent associés à `data/referentiel-v1.json` pour conserver la signification de leurs numéros. Un nouveau dossier utilise la grille complète. Supprimer le dernier justificatif d’un critère AJO le fait repasser à « Preuve manquante ».

## Limites connues (V1)

- Pas de conversion HEIC→JPG automatique (installer Pillow si besoin) : les photos
  iPhone en .heic sont stockées telles quelles.
- Une invitation contenant `localhost` fonctionne uniquement sur le poste qui héberge le serveur. La console de production génère le lien HTTPS public.

Visuel de l’espace invité : [camping en bord de mer, BusterTravel sur Pinterest](https://fr.pinterest.com/pin/1098878377851832416/). Logo fourni par le propriétaire de CampCompagnon.
