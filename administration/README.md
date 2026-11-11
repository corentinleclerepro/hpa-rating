# Hpa Rating · Camp Compagnon — Espace administration

L’opérateur saisit son mot de passe, puis les six chiffres reçus par e-mail. Le code est valable dix minutes dans le navigateur qui l’a demandé. Un code de secours permet aussi une connexion avec le mot de passe. Depuis l’administration, l’opérateur peut traiter les demandes d’accès, copier les invitations, remplacer les codes perdus et révoquer un accès. [Installation de l’administration HTTPS](../deploy/supabase/README.md)

## Essai local

Configurer dans l’environnement de l’administration `HPA_ADMIN_EMAIL` (boîte de réception du propriétaire) et `HPA_ADMIN_MAIL_KEY` (clé Resend d’envoi sur le domaine de l’expéditeur). L’expéditeur est `administration@devora-agency.fr`.

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
