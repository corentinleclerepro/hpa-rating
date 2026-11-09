# ⭐ Prépa Classement Camping & PRL (Atout France)

Outil **local** (aucune donnée ne quitte la machine) pour préparer un dossier de
classement en étoiles (1★–5★) d'un terrain de camping / caravanage ou d'un PRL,
selon le tableau de classement officiel (arrêté du 10 avril 2019, annexe I).

## Fonctionnalités

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

## Lancement

```bash
python3 run.py            # http://127.0.0.1:8000
python3 run.py --port 9000
```

Zéro dépendance externe (Python 3.10+ standard library uniquement).
Données dans `data/` (base SQLite + preuves + exports).

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Référentiel

`data/referentiel.json` est seedé à partir du PDF officiel Atout France
(critères 1–52, extraits, marqués `"validated": false`). **À faire avant usage
en production** : compléter et valider critère par critère depuis le PDF
(champ `"validated": true`, source + page), le fichier est rechargé à chaud.

## Limites connues (V1)

- Référentiel partiel (à compléter/valider) ; pas d'édition des critères dans l'UI.
- Pas de conversion HEIC→JPG automatique (installer Pillow si besoin) : les photos
  iPhone en .heic sont stockées telles quelles.
- Utilisateur unique local (pas d'authentification) : lancer en `127.0.0.1` par défaut.
