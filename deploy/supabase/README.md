# Hpa Rating sur Vercel et Supabase

Après la création de la boîte des demandes (`access_requests.sql`), appliquer `erase_refused_requests.sql` avant de publier l’interface de refus. Cette migration efface les demandes déjà refusées et installe l’effacement dans la transaction de chaque futur refus. Les rôles applicatifs conservent leurs droits existants.

Pour le mini-dossier, appliquer [starter.sql](starter.sql) après la création du rôle web de l’administration et avant de publier les deux services. Cette migration ajoute les copies jointes aux demandes, le suivi des reprises et les compteurs quotidiens.

L’espace invité est une application Django sur Vercel. Les dossiers, les sessions, les invitations et les pièces se trouvent dans le schéma PostgreSQL privé `hpa_rating`. Les fichiers sont divisés en parties de 1 Mio, avec une limite de 64 Mio par envoi. Ils consomment le quota **disque de la base PostgreSQL**. Une copie d’un dossier partage les octets immuables de ses pièces. La suppression de la dernière référence efface ces octets dans la même transaction.

Les fichiers passent par les routes Django, qui contrôlent le propriétaire et l’étape du dossier. Le rôle `hpa_rating_guest` gère les dossiers et les sessions des campings. Le formulaire public écrit les demandes par une fonction dédiée. Leur lecture est réservée au service d’administration.

Pour une installation neuve, appliquer [schema.sql](schema.sql) au projet Supabase choisi. Ce script crée les tables et deux rôles initialement sans connexion. Attribuer indépendamment à chacun un mot de passe aléatoire, activer son droit `LOGIN` et conserver les mots de passe dans les secrets de chaque service. Les deux services utilisent la même clé aléatoire `HPA_INVITATION_KEY` pour reconnaître les codes. La clé Django de l’espace invité est distincte.

Pour Vercel, importer le dépôt dans un projet dédié et définir les variables **Production** suivantes. `HPA_SUPABASE_ROLE` vaut `guest`. `HPA_SUPABASE_PROJECT` contient la référence du projet, `HPA_DB_HOST` l’hôte du pooler indiqué par Supabase, et `HPA_DB_PASSWORD` le mot de passe du rôle invité. Ajouter `HPA_INVITATION_KEY`, `HPA_CLOUD_APP_KEY` (deux secrets distincts d’au moins 40 caractères) et `HPA_GUEST_ORIGIN=https://hpa-rating.campcompagnon.fr`. L’entrée Python est déclarée dans `pyproject.toml`. Seul le port PostgreSQL 6543 du pooler est utilisé et son certificat est validé avec l’autorité Supabase fournie.

Pour essayer l’application pendant le raccordement DNS, définir aussi `HPA_VERCEL_ALIAS` avec l’alias de production exact attribué au projet, par exemple `hpa-rating.vercel.app`. Les invitations continuent de pointer sur l’origine personnalisée.

## Espace administration en ligne

Après le schéma initial, appliquer successivement [la boîte de demandes](access_requests.sql) et [le schéma privé de l’administration](web_admin.sql). Attribuer un mot de passe aléatoire et le droit `LOGIN` au seul nouveau rôle `hpa_rating_webadmin`. Il gère les demandes et les invitations et conserve son authentification dans `hpa_rating_staff`.

Appliquer [admin_email.sql](admin_email.sql) pour créer la table des codes à usage unique dans le schéma privé. Elle conserve une empreinte du code, sa date d’expiration et le nombre d’essais. Un nouvel envoi remplace le code précédent.

Préparer un répertoire vide avec `python deploy/stage_admin.py CHEMIN` et le publier dans le projet Vercel de l’administration. Les variables de Production reprennent la référence Supabase, le pooler, l’origine invitée et la clé des invitations. Utiliser `HPA_SUPABASE_ROLE=webadmin`, son propre `HPA_DB_PASSWORD`, une nouvelle `HPA_CLOUD_APP_KEY` et `HPA_ADMIN_HOST` avec le nom d’hôte HTTPS. Dans ce même projet, configurer `HPA_ADMIN_EMAIL` avec l’adresse du propriétaire et `HPA_ADMIN_MAIL_KEY` avec une clé Resend sensible limitée à l’envoi depuis le domaine `devora-agency.fr`.

Dans un environnement privé muni de cette configuration, lancer une seule fois `python deploy/prepare_admin.py CHEMIN_PRIVE.txt`. Cette commande applique les migrations Django dans le schéma privé et prépare une clé d’activation valable 24 heures. Révoquer ensuite le droit `CREATE` du rôle sur `hpa_rating_staff` jusqu’à la prochaine migration de structure. Le propriétaire ouvre le site, saisit la clé, choisit son mot de passe et confirme le code reçu par e-mail. Il conserve les huit codes de secours pour accéder à l’administration en cas de perte d’accès à sa boîte.

## Variante locale pour le développement

Sur Windows, [console.ps1](console.ps1) lit la configuration opérateur chiffrée avec DPAPI pour l’utilisateur connecté. Elle contient les mêmes noms de variables, avec `HPA_SUPABASE_ROLE=admin`, le mot de passe propre au rôle d’administration et un `HPA_DATA_DIR` privé pour le second facteur. Exécuter avec `-Configuration <fichier.dpapi> -PreparerPremierAcces` pour produire la fiche initiale, puis avec `-Configuration <fichier.dpapi>` pour ouvrir le service sur le port local 8002.

Rattacher uniquement le sous-domaine Hpa Rating à ce projet Vercel en utilisant la valeur DNS indiquée par Vercel. Après émission du certificat, lancer `python deploy/verify.py https://hpa-rating.campcompagnon.fr` et essayer une invitation réelle. Une invitation révoquée doit perdre l’accès au prochain appel. La sauvegarde du projet Supabase inclut les pièces stockées dans ces tables. Conserver aussi une copie privée des clés de l’application et de la console.
