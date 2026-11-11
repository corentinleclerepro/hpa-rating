# Mettre Hpa Rating en ligne

Les campings utiliseront **https://hpa-rating.campcompagnon.fr/connexion** avec leur code. L’opérateur ouvrira **http://127.0.0.1:18001/** après avoir établi son tunnel SSH. Il n’y a ni adresse d’administration publique ni mot de passe par défaut.

## 1. Préparer la machine gratuite

Dans la [console Oracle Cloud](https://cloud.oracle.com/), rester sur le compte gratuit et dans sa région d’origine. Vérifier les ressources **déjà consommées** et l’éligibilité de chaque choix. Pour cette application, une VM dédiée Ubuntu Server 24.04 LTS, `VM.Standard.A1.Flex` avec **1 OCPU et 4 Go de RAM**, un disque de démarrage standard de **50 Go** et une IPv4 publique suffit pour démarrer. Si le quota gratuit restant est insuffisant ou la forme indisponible, attendre ou essayer un autre domaine de disponibilité de la même région. Ne pas prendre une VM payante ni activer d’option facturée. [Ressources Always Free et récupération des instances inactives](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Utiliser un sous-réseau public dédié avec une route vers la passerelle Internet. Autoriser en entrée **TCP 80 et 443** depuis Internet et **TCP 22** depuis l’IP publique de l’opérateur (`/32`). Vérifier aussi les règles de la liste de sécurité du sous-réseau : elles s’ajoutent à celles du groupe de sécurité. Garder les ports 18100 et 18101 fermés dans le réseau public. Associer uniquement la **clé SSH publique** de l’opérateur à la VM.

Dans les options avancées de création, fournir [cloud-init.yaml](cloud-init.yaml) comme script d’initialisation. Il installe Docker et Compose depuis les dépôts Ubuntu et ajoute au pare-feu IPv4 de la VM uniquement les deux ports web. Il conserve les règles Oracle existantes. [Recommandations Oracle pour le pare-feu](https://docs.oracle.com/en-us/iaas/Content/Compute/References/bestpracticescompute.htm#essfirewall).

## 2. Installer la version et vérifier les services privés

Sur le poste de travail, utiliser l’archive de déploiement fournie, ou la créer depuis la révision Git à déployer :

```sh
git archive --format=tar.gz --prefix=Hpa-Rating/ -o ../Hpa-Rating-deploiement.tar.gz HEAD
scp ../Hpa-Rating-deploiement.tar.gz ubuntu@IP_VM:
```

Remplacer `IP_VM` par l’adresse effectivement attribuée. Se connecter avec `ssh ubuntu@IP_VM` et vérifier l’empreinte SSH du serveur au premier accès. Sur la VM neuve :

```sh
cloud-init status --wait
sudo docker compose version
mkdir -m 700 ~/hpa-version-1
tar -xzf ~/Hpa-Rating-deploiement.tar.gz --strip-components=1 -C ~/hpa-version-1
cd ~/hpa-version-1
sudo docker compose -f deploy/compose.yaml up --build -d guest admin
sudo docker compose -f deploy/compose.yaml ps
```

Après le démarrage, cette commande doit réussir **sur la VM** :

```sh
curl -fsS -o /dev/null -H 'Host: hpa-rating.campcompagnon.fr' -H 'X-Forwarded-Proto: https' http://127.0.0.1:18100/connexion
curl -fsS -o /dev/null http://127.0.0.1:18101/
ss -ltn | grep -E '18100|18101'
```

Les deux adresses d’écoute doivent être **127.0.0.1**. Les images construites ne contiennent ni dossier utilisateur ni code d’invitation utilisable ; l’exemple fictif reste disponible après connexion. L’archive se transfère par SSH : la VM n’a pas besoin d’un jeton GitHub.

## 3. Raccorder Hostinger et tester HTTPS depuis l’extérieur

Dans la zone DNS de `campcompagnon.fr`, vérifier que le nom `hpa-rating` est libre. Ajouter seulement **A · hpa-rating · IP de la VM · TTL 300** (ou le minimum accepté). Laisser les autres enregistrements en place. Ne pas ajouter de deuxième adresse ou d’AAAA sans service IPv6 opérationnel.

Une fois que le DNS public renvoie l’IP attendue, démarrer Caddy sur la VM :

```sh
sudo docker compose -f deploy/compose.yaml up -d edge
sudo docker compose -f deploy/compose.yaml logs --tail 25 edge
```

Caddy obtient et renouvelle le certificat grâce aux ports 80/443 ; il ne relaie que les requêtes vers l’espace invité. [HTTPS automatique de Caddy](https://caddyserver.com/docs/automatic-https). Depuis une autre machine, lancer :

```sh
python deploy/verify.py https://hpa-rating.campcompagnon.fr
```

Ce contrôle exige un certificat reconnu **pour ce nom**, la redirection HTTP vers HTTPS, des cookies sécurisés, un refus d’accès aux dossiers sans invitation et une réponse 404 pour l’administration. Ne communiquer l’adresse aux campings qu’après ce contrôle et un essai avec une invitation jetable.

## 4. Ouvrir la console et créer la première invitation

Sur le PC de l’opérateur, garder ce tunnel ouvert pendant l’utilisation de la console :

```sh
ssh -o ExitOnForwardFailure=yes -N -L 127.0.0.1:18001:127.0.0.1:18101 ubuntu@IP_VM
```

**Première configuration uniquement :** depuis un second terminal SSH privé sur la VM, dans le répertoire de la version :

```sh
sudo docker compose -f deploy/compose.yaml exec -T admin python run_admin.py --port 18001 --setup-key /tmp/premier-acces.txt
sudo docker compose -f deploy/compose.yaml exec -T admin cat /tmp/premier-acces.txt
```

Configurer `HPA_ADMIN_EMAIL` et `HPA_ADMIN_MAIL_KEY` pour le service admin. Sur son PC, ouvrir [la console par le tunnel](http://127.0.0.1:18001/). Saisir la clé valable 24 h, choisir son mot de passe, confirmer le code reçu par e-mail et conserver ses codes de secours. Après activation, effacer la fiche privée du conteneur avec `sudo docker compose -f deploy/compose.yaml exec -T admin rm /tmp/premier-acces.txt`.

Créer une invitation d’essai, la copier et l’utiliser dans une fenêtre privée sur le domaine HTTPS. Ouvrir l’exemple, vérifier un justificatif puis révoquer le code dans la console : au prochain accès, la fenêtre invitée doit refuser le dossier. Les invitations suivantes pourront être copiées puis envoyées personnellement aux campings. Fermer le tunnel ne coupe pas leur accès.

## Sauvegarder, restaurer et mettre à jour

Les volumes persistants `guest_state` (dossiers, PDF, exports), `admin_state` (compte, second facteur), `invitations` (registre et clé d’empreinte), `tls` et `caddy_config` survivent au remplacement des conteneurs. Ne jamais lancer `docker compose down -v` sur l’installation en service. Sans les clés correspondantes, restaurer seulement les bases ne suffit pas.

- Depuis le répertoire de la version : `sudo sh deploy/backup.sh`. La commande arrête brièvement les services en cours, vérifie les cinq archives, puis redémarre les mêmes services. Le résultat est dans `/var/backups/hpa-rating/<date UTC>/`, accessible uniquement à root. Conserver régulièrement une copie **chiffrée hors de la VM**, notamment avant chaque mise à jour ; un disque de la même VM ne protège pas contre sa perte.
- Pour restaurer, utiliser une **VM neuve dédiée**. Installer la même version, exécuter `sudo docker compose -f deploy/compose.yaml build` puis `sudo docker compose -f deploy/compose.yaml create` **sans démarrer les services**. Copier une sauvegarde de confiance sur la VM puis lancer `sudo python3 deploy/restore.py /chemin/vers/la-sauvegarde`. Le programme vérifie les empreintes et refuse d’écraser un volume déjà utilisé. Démarrer les services, vérifier le site, une invitation conservée, un PDF et l’accès opérateur.
- Pour changer de version, sauvegarder puis extraire la nouvelle archive dans un **nouveau répertoire**. Depuis ce répertoire, lancer `sudo docker compose -f deploy/compose.yaml up --build -d`. Le nom Compose `hpa-rating` est fixe : les volumes restent les mêmes. Si la version a modifié le format des données, restaurer la sauvegarde sur une VM neuve pour revenir en arrière.

Une première installation démarre vide : le registre et les dossiers de test du PC ne sont pas envoyés. Si des codes ou des dossiers locaux doivent être repris, prévoir une migration privée avant d’ouvrir le site. Ne jamais transférer le répertoire local `data/` dans une image ni fusionner les données de la console et des invités.
