# Hpa Rating · Camp Compagnon — Espace invité

Application de préparation au classement des campings et PRL. Entrer son code personnel pour créer, reprendre ou exporter ses dossiers.

Le bouton de reprise ouvre le premier numéro applicable non renseigné. Confirmer le profil puis suivre les prérequis et critères dans l’ordre. Les boutons **?** expliquent comment faire et ce que chaque choix change. La revue des justificatifs ouvre la synthèse ; les réponses précédentes restent modifiables.

Depuis le répertoire qui contient `run.py`, avec Python 3.10 ou ultérieur :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# Lors d’une installation séparée : indiquer le répertoire de données HPA existant.
$env:HPA_DATA_DIR = 'C:\chemin\vers\les\donnees-HPA'
.venv\Scripts\python run.py
```

Ouvrir [Mon espace](http://localhost:8000/espace). La grille des 195 critères et les trois justificatifs de l’exemple sont inclus. Le registre d’invitations doit être celui qui a émis le code. L’espace continue de fonctionner seul une fois les codes créés.
