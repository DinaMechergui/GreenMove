# Mobility Tracker et service carbone

## État

`tracker` est maintenant une application Django fonctionnelle pour l'enregistrement web, la consultation, la correction et la suppression des trajets du propriétaire. `carbon_service` expose une interface Python partagée. Le dépôt n'inclut pas les PDF d'équipe/validation ni un jeu Geolife annoté. Le modèle LightGBM, les métriques associées, le déploiement et la conformité complète à la grille ne peuvent donc pas être déclarés validés.

## Architecture intégrée

- Application déjà enregistrée sous `tracker.apps.TrackerConfig`; ses URL sont déjà incluses par le projet à `/tracker/`.
- Authentification commune via `AUTH_USER_MODEL = accounts.CustomUser`, sessions Django, `login_required`, CSRF middleware et filtrage du propriétaire dans chaque vue.
- Modèles `Trip`, `GPSPoint`, `TripSegment`; les coordonnées sont stockées uniquement sous forme de chiffré Fernet. Un UUID de requête de trajet et un numéro de séquence de point rendent les reprises idempotentes.
- Les trajets et leurs relations supprimés sont effacés en cascade. Le mode « détecté » reste distinct du mode confirmé manuellement.
- Les données GPS ne sont déchiffrées que dans les vues privées de détail/export ou pendant un traitement métier authentifié.

## Écrans et URLs

- `GET /tracker/`: dashboard, historique paginé et filtres date/mode.
- `POST /tracker/trips/start/`: démarrage protégé par session/CSRF.
- `GET /tracker/trips/<uuid>/`: détail privé, carte Leaflet, segments et état de traitement.
- `POST /tracker/trips/<uuid>/points/`: réception JSON d'un point chiffré avant l'écriture.
- `POST /tracker/trips/<uuid>/complete/`: calcul de distance, vérification de plausibilité et demande de classification.
- `GET|POST /tracker/trips/<uuid>/edit/`, `GET|POST .../delete/`: CRUD propriétaire.
- API DRF sous `/tracker/api/trips/`: `GET|POST` pour la liste/démarrage; `GET|PATCH|PUT|DELETE /<uuid>/` pour les trajets du propriétaire; `POST /<uuid>/points/` pour les points; `POST /<uuid>/complete/` pour terminer. Elle utilise l'authentification DRF configurée par le projet et n'inclut jamais les coordonnées GPS dans le serializer de trajet.
- `GET /tracker/trips/<uuid>/compare/`: estimations comparatives à distance identique, explicitement non routées.
- `GET|POST /tracker/import/gpx/`, `GET /tracker/trips/<uuid>/export.gpx`: GPX borné et limité au propriétaire.
- `GET /tracker/manifest.webmanifest`, `/tracker/service-worker.js`, `/tracker/offline/`: socle PWA et écran hors-ligne.

Les points doivent porter latitude/longitude valides, un horodatage avec fuseau et des mesures dans les bornes définies par `tracker.services.trip_service.add_point`. Les erreurs client sont des réponses 400/413 explicites. Une répétition identique du point renvoie 200 sans doublon; un numéro de séquence réutilisé pour d'autres données est refusé.

## GPS et confidentialité

Fournir `GPS_ENCRYPTION_KEY`, secret aléatoire d'au moins 32 caractères, par le gestionnaire de secrets du déploiement (ne pas le versionner). Le service dérive une clé Fernet compatible et chiffre latitude et longitude séparément. Changer la variable rend les anciennes données indéchiffrables: prévoir une rotation contrôlée avant de changer la clé. Fernet ne protège pas contre une compromission de l'application ou de sa clé.

La file hors-ligne utilise IndexedDB et WebCrypto AES-GCM avec une clé non exportable; les points ne sont pas mis en cache par le Service Worker. Le navigateur contrôle toutefois simultanément l'origine et la clé; cette mesure ne protège pas contre une XSS ou un navigateur compromis. L'utilisateur doit être connecté pour synchroniser. La capture continue tant que l'écran actif reste ouvert; aucun Background Sync n'est prétendu.

Le map-matching OSRM et Overpass sont des fonctions explicites dans `tracker.services.route_matching`. Ils ne sont pas appelés pendant la capture et aucune position exacte n'est envoyée à ces tiers automatiquement. Si ces fonctions sont exposées à l'interface, demander un consentement clair avant l'envoi des coordonnées.

## Classification IA

`tracker.services.transport_classifier.extract_features` extrait vitesse moyenne/maximale/écart-type, accélération, ratio d'arrêts, précision et volume de points. `predict_transport` charge uniquement un artefact configuré par `TRANSPORT_MODEL_PATH`; si le modèle ou LightGBM manque, il renvoie `status=unavailable` et ne crée aucune prédiction heuristique.

Aucun artefact ni dataset Geolife annoté n'est livré dans ce dépôt. Le pipeline est maintenant disponible via `python manage.py train_transport_model --data-dir <Geolife> --output <model.joblib>`; il tient les utilisateurs du test à l'écart et écrit les métriques dans un fichier `.metrics.json`. La commande n'a pas été exécutée sur un jeu réel dans cette installation, donc aucune performance ne peut encore être revendiquée. Une réponse « modèle indisponible » demeure attendue tant qu'un artefact réel n'est pas configuré. L'inférence est synchrone à ce stade; aucun Celery/Redis worker n'est configuré.

`GPS_ENCRYPTION_KEY` et `TRANSPORT_MODEL_PATH` sont lus par la configuration Django (variables d'environnement ou source `python-decouple`). Le secret GPS est obligatoire pour écrire/lire des coordonnées; il ne doit pas être versionné. Après avoir défini une clé persistante dans l'environnement local ou de déploiement, redémarrer les processus Django. Une clé nouvellement générée ne déchiffrera jamais des coordonnées qui auraient été chiffrées avec une ancienne clé.

## Calcul carbone partagé

API stable dans `carbon_service.services`:

```python
calculate_trip_emissions(distance_km, transport_mode)
calculate_segment_emissions(distance_km, transport_mode)
calculate_alternative_emissions(distance_km, transport_mode)
calculate_carbon_savings(baseline_kg, alternative_kg)
get_emission_factor(transport_mode)
calculate_segments_total(segments)
```

Distance en passager-km, facteurs en kg CO2e/passager-km; le résultat d'un trajet est arrondi au centième. Les facteurs routiers reprennent la table passager transport DEFRA 2024 indiquée dans `carbon_service.factors`. Marche et vélo valent zéro en émissions directes de déplacement uniquement, pas sur leur cycle de vie complet. Ces estimations ne modélisent ni l'occupation réelle, ni le carburant/véhicule, ni le routage tunisien.

EcoPlanner/EcoRewards ne consomment actuellement pas cette interface: leurs vues existantes sont des placeholders. Le trajet expose les champs nécessaires au contrat, mais aucune attribution de points ou connexion inter-module n'est déclarée.

## Installation et lancement local

```powershell
python -m pip install -r requirements.txt
$env:GPS_ENCRYPTION_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
python manage.py migrate
python manage.py runserver
```

Accéder à `http://127.0.0.1:8000/tracker/` après connexion. Le GPS navigateur exige HTTPS ou localhost. PostgreSQL est la base locale par défaut; pour utiliser SQLite, définir `DB_ENGINE=sqlite`. PostGIS n'a pas été configuré ni testé.

Pour Render, suivre la section « Déploiement sur Render » du [README](../README.md).
La configuration de production utilise `DATABASE_URL`, WhiteNoise et Daphne;
la préparation n'implique pas qu'un service Render réel ait été déployé ou testé.

## Contrats intégrateurs

Pour un trajet, l'identifiant UUID, le propriétaire, distance, durée, modes détecté/confirmé, CO2e et statut/indicateurs anti-triche sont disponibles comme attributs du modèle `Trip`. Un consommateur de récompenses doit accepter uniquement les trajets valides selon sa politique et utiliser `Trip.id` comme clé d'idempotence. Ne pas exposer les `GPSPoint` à Planner, Rewards ou MobilityMatch sans permission et consentement dédiés.

Les contrats OpenAPI des autres applications, Celery, les systèmes de récompenses et les interfaces de partage n'existent pas dans leur implémentation actuelle.

## Vérifications réalisées

La suite complète du projet a passé **96 tests**; les tests `tracker` et `carbon_service` en comptent **44**. `manage.py check` et `makemigrations --check --dry-run` passent. La couverture métier mesurée pour ces deux paquets est **90%** selon le périmètre détaillé dans [roua_tests.md](./roua_tests.md). `check --deploy` n'a pas signalé d'avertissement de sécurité Django, mais a rapporté quatre avertissements de schéma OpenAPI (un enum Tracker et trois API MobilityMatch); ce contrôle ne constitue pas un déploiement. Les tests d'accessibilité navigateur, PostgreSQL/PostGIS et infrastructure Celery/Redis restent à réaliser.
