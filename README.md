# Mail ⇄ Jira — Signarama

Service qui lit la boîte mail de support, décide grâce à un LLM si un mail doit devenir un ticket Jira
(projet `KAN`), puis garde le **statut du ticket** et le **dossier du mail** synchronisés dans les deux sens.
Le demandeur et les administrateurs sont prévenus par mail à chaque évolution.

## Ce qui a été fait, étape par étape

### 1. Mise en place du projet
- Projet Python dans `C:\JIRA`.
- Identifiants (boîte mail, Jira, clé Anthropic) placés dans un fichier `.env`, exclu de git (`.gitignore`) ; `.env.example` sert de modèle sans secrets.
- Boîte lue en IMAP SSL (`signarama.powermail.fr`, port 993), envoi en SMTP SSL (port 465).

### 2. Mail → Jira (création des tickets)
- Lecture de la boîte `INBOX` en **lecture seule** (rien n'est marqué comme lu).
- Un agent Claude (Claude Agent SDK) lit le contenu du mail et décide s'il s'agit d'une demande actionnable.
- Il cherche d'abord un ticket existant sur le même sujet pour éviter les doublons, puis crée le ticket via le serveur MCP `mcp-atlassian`.
- Le contenu du mail est traité comme une donnée non fiable : l'agent n'exécute jamais d'instructions qu'il contient.
- Titre du ticket au format `<Entreprise> - <titre>` (ex. « Signarama Bordeaux Est - … »), l'entreprise étant déduite de la signature ou du texte du mail.
- Description structurée : résumé, expéditeur, date, détails, échéances.

### 3. Quels mails sont pris en compte
- Mails **non lus** de `INBOX`, **ou** reçus depuis moins de `WINDOW_MINUTES` (60 par défaut), qu'ils aient été ouverts ou non.
- Un mail déjà traité n'est jamais retraité (mémoire dans `data/processed.json`).

### 4. Pièces jointes
- Toutes les pièces jointes et images sont ajoutées au ticket via l'API Jira.
- Seuls les **logos de signature récurrents** (même image dans plusieurs mails) sont écartés ; l'historique est amorcé au premier démarrage (`data/image_hashes.json`).
- Un fichier de plus de 10 Mo n'est pas joint : la description l'indique.
- L'agent ne mentionne que les fichiers réellement joints.

### 5. Mail → Jira (statut selon le dossier)
Quand un mail est rangé dans un dossier, son ticket change de statut :

| Dossier | Statut Jira |
|---|---|
| `00 - Message Pris en Compte` | Planifier |
| `01 - A traiter par Wiem` | En cours |
| `02 - A traiter par Philippe` | En cours |
| `03 - Traitement terminé` | Terminé |
| `04 - Idées améliorations à conserver` | Idée |

Une réponse dans la même conversation est rattachée au même ticket.

### 6. Jira → Mail (dossier selon le statut)
Quand le statut d'un ticket change dans Jira, le mail est déplacé :

| Statut Jira | Dossier |
|---|---|
| Nouvelle demande | `INBOX` |
| Planifier | `00` |
| En cours | `01` (Wiem) — un mail déjà en `02` ne bouge pas |
| En revue | aucun déplacement |
| Terminé | `03` |
| Idée | `04` |

Jira est interrogé à chaque passage (pas en temps réel). Chaque changement n'est appliqué qu'une fois dans un sens ou dans l'autre, pour éviter les boucles.

### 7. Mails automatiques
- **Au demandeur**, à la création du ticket puis à chaque changement de statut : message poli et professionnel (référence, intitulé, statut, lien vers le ticket). Textes dans `notify.py` (`TEMPLATES`).
- **Aux administrateurs** (`ADMIN_MAILS`), à chaque création et changement de statut : référence, intitulé, ancien → nouveau statut, demandeur, lien.
- Un mail n'est envoyé qu'une fois par couple (ticket, statut) (`data/notified.json`).
- Seuls les tickets créés depuis la mise en place des notifications sont concernés.

### 8. Modes `dev` et `prod`
- `MODE=dev` : le mail au demandeur part uniquement vers `DEV_MAILS`, avec `[DEV]` dans l'objet et la ligne « [MODE DEV] Destinataire réel en production : … ».
- `MODE=prod` : le mail part au vrai demandeur ; `DEV_MAILS` n'est plus utilisé.
- `ADMIN_MAILS` reçoit les mails admin dans les deux modes (avec la mention `[MODE DEV]` seulement en dev).
- Une liste vide (`DEV_MAILS` ou `ADMIN_MAILS`) ne provoque aucune erreur : les mails concernés ne sont simplement pas envoyés.

### 9. Exécution avec Docker
- `Dockerfile` (Python 3.12 slim, utilisateur non-root) et `docker-compose.yml`.
- Le service relance un passage toutes les `POLL_INTERVAL` secondes (120 s actuellement) et redémarre automatiquement.
- L'état est conservé dans `./data` (monté dans le conteneur) : fonctionne sous Linux comme sous Windows.

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `main.py` | Boucle principale : lecture des mails, agent LLM, création des tickets |
| `folders.py` | Mail → Jira : statut du ticket selon le dossier du mail |
| `jira_to_mail.py` | Jira → Mail : déplacement du mail selon le statut du ticket |
| `mail_move.py` | Recherche et déplacement d'un mail par son Message-ID (IMAP) |
| `notify.py` | Mails au demandeur et aux administrateurs |
| `jira_api.py` | Appels REST Jira (pièces jointes, statuts, transitions) |
| `logos.py` | Détection des logos de signature récurrents |
| `state.py` | Mémoire : mail ↔ ticket ↔ dernier statut appliqué |
| `config.py` | `MODE`, `DEV_MAILS`, `ADMIN_MAILS`, choix des destinataires |
| `Dockerfile`, `docker-compose.yml` | Exécution en conteneur |
| `data/` | `processed.json`, `image_hashes.json`, `notified.json` |

## Configuration (`.env`)

| Variable | Rôle |
|---|---|
| `IMAP_HOST`, `IMAP_PORT`, `SMTP_HOST`, `SMTP_PORT` | Serveur mail |
| `MAIL_USER`, `MAIL_PASSWORD` | Boîte surveillée (`kosmo@signarama.fr`) |
| `JIRA_URL`, `JIRA_USERNAME`, `JIRA_TOKEN` | Accès Jira |
| `JIRA_PROJECT_KEY`, `JIRA_ISSUE_TYPE` | Projet (`KAN`) et type de ticket (`Task`) |
| `ANTHROPIC_API_KEY` | Clé pour l'agent LLM |
| `MODE` | `dev` ou `prod` |
| `DEV_MAILS` | Destinataires des mails du demandeur en mode dev (séparés par des virgules) |
| `ADMIN_MAILS` | Administrateurs prévenus (séparés par des virgules) |
| `DRY_RUN` | `true` = simulation, rien n'est créé ni envoyé |
| `WINDOW_MINUTES` | Fenêtre des mails récents, en plus des non lus (défaut 60) |
| `POLL_INTERVAL` | Intervalle entre deux passages, en secondes |
| `LOGO_MIN_MAILS` | Nombre d'autres mails à partir duquel une image est un logo (défaut 3) |

## Commandes utiles

```bash
docker compose up -d --build   # construire et démarrer (après un changement de code)
docker compose up -d           # recréer après un changement du .env
docker compose restart         # forcer un passage immédiat
docker compose logs -f         # suivre l'activité (Ctrl+C n'arrête pas le service)
docker compose ps              # vérifier que le conteneur tourne
docker compose down            # arrêter
```

Pour retester un mail : le remettre en non lu (ou le recevoir depuis moins de 60 min) et retirer son entrée de `data/processed.json`.

## Limites connues
- Seuls les mails de `INBOX` donnent lieu à un ticket ; un mail rangé dans un dossier avant d'avoir été lu par le script n'a pas de ticket.
- Seuls les tickets créés depuis le suivi des statuts sont reliés à leur mail.
- Les numéros de devis du type `DVS-2026-1262` peuvent être transformés en lien par Jira dans la description.
- Jira est consulté à intervalle régulier : un changement de statut peut mettre jusqu'à `POLL_INTERVAL` secondes à être répercuté.
- Les secrets ont été échangés pendant la conception : pensez à les renouveler.
