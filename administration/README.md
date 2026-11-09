# Hpa Rating · Camp Compagnon — Console privée d’invitations

Cette application peut tourner sans le serveur des campings. Elle gère uniquement les invitations. Le premier accès utilise une clé locale, un mot de passe et une application d’authentification.

Depuis le répertoire qui contient `run_admin.py`, avec Python 3.10 ou ultérieur :

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# Pour les distributions décompressées séparément : indiquer le répertoire de données existant, identique pour les deux processus.
$env:HPA_DATA_DIR = 'C:\chemin\vers\les\donnees-HPA'
# Première configuration uniquement, si vous n’avez pas encore de clé :
.venv\Scripts\python run_admin.py --setup-key ..\configuration-hpa.txt
.venv\Scripts\python run_admin.py
```

Ouvrir [la console](http://127.0.0.1:8001/). Les invitations à copier contiennent le lien vers l’espace invité (par défaut `http://localhost:8000/connexion`). Si l’adresse invitée change, définir `HPA_GUEST_ORIGIN` avant de lancer la console. Il est possible d’arrêter la console dès que les codes sont prêts.
