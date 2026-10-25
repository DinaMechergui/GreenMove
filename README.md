# 🌱 GreenMove - Plateforme Intelligente de Mobilité Durable

> **Hackathon Climat & IA 2026** — Projet développé en équipe de 5 personnes.  
> Mobilité décarbonée, mutualisation des trajets et intelligence artificielle pour le Grand Tunis.

Consultez le fichier `README.md` situé à la racine du projet pour la documentation complète et les instructions de démarrage.

## Démarrage local avec PostgreSQL

PostgreSQL est la base utilisée par défaut. Démarrez Docker Desktop et, pour
une nouvelle installation, copiez `.env.example` vers `.env`.

Dans PowerShell, depuis la racine du projet :

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose up -d db
python manage.py migrate
python manage.py runserver
```

Compose démarre PostgreSQL 16 sur `localhost:5432` avec un volume persistant.
La configuration utilise les variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`
et `DB_PORT` dans `.env`.
Pour revenir à SQLite en développement, définissez `DB_ENGINE=sqlite`.

## Déploiement sur Render

Créez une base PostgreSQL et un service Web Render dans la même région, liés
au dépôt GitHub. Configurez le service ainsi :

- **Build Command** : `bash build.sh`
- **Start Command** : `daphne -b 0.0.0.0 -p $PORT config.asgi:application`
- **`DJANGO_SETTINGS_MODULE`** : `config.settings.prod`
- **`DATABASE_URL`** : URL interne de la base PostgreSQL Render
- **`SECRET_KEY`** : secret Django fort et aléatoire
- **`GPS_ENCRYPTION_KEY`** : secret aléatoire d'au moins 32 caractères

Render fournit `RENDER_EXTERNAL_HOSTNAME`; la configuration production l'utilise
pour `ALLOWED_HOSTS` et `CSRF_TRUSTED_ORIGINS`. Pour un domaine personnalisé,
définissez explicitement ces deux variables. Le build collecte les fichiers
statiques avec WhiteNoise puis applique les migrations. Conservez et
sauvegardez `GPS_ENCRYPTION_KEY` : la changer rend les coordonnées déjà
enregistrées indéchiffrables.

Daphne est utilisé à la place de Gunicorn/Uvicorn afin de servir l'application
ASGI et les WebSockets Django Channels. Le canal en mémoire convient à une
instance unique seulement; un déploiement multi-instance nécessite Redis.
Celery et un worker de classification IA ne sont pas configurés. La présence
de cette configuration ne vaut pas validation d'un déploiement Render réel.
