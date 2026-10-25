# Rapport de tests Mobility Tracker

## Environnement et commandes

Projet observé sous Python 3.14.7 et Django 5.2. Un `requirements.txt` a été ajouté pour décrire les dépendances importées par le projet et les besoins du module.

Commandes de validation à exécuter après installation:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tracker carbon_service
python -m coverage run --source=tracker,carbon_service --omit='*/tests.py,*/migrations/*,tracker/admin.py,tracker/apps.py,tracker/urls.py' manage.py test tracker carbon_service
python -m coverage report -m
```

## État initial observé

Avant l'ajout des dépendances, `python manage.py check` échouait à charger `config.settings` avec `ModuleNotFoundError: No module named 'decouple'`. L'environnement Pylance ne signalait que Django 5.2, alors que le dépôt configure aussi DRF, Channels, crispy forms, `django-htmx`, `python-decouple` et d'autres packages.

## Tests ajoutés

`tracker/tests.py` couvre calcul carbone, validation/chiffrement GPS, distance haversine, GPX valide/invalide, détection de téléportation, GPS imprécis, absence de modèle, segmentation de données trop courtes, auth, CRUD web et REST, isolation des trajets, synchronisation idempotente, import/export et cascade.

`carbon_service/tests.py` teste unités/facteurs, arrondis, distances nulles, mélanges de modes et économies signées.

## Résultats mesurés

- `python manage.py test`: **96 tests réussis**, aucune erreur.
- `python manage.py test tracker carbon_service`: **44 tests réussis**.
- `python manage.py makemigrations --check --dry-run`: aucune migration manquante.
- `python manage.py check`: aucune anomalie.
- `DJANGO_SETTINGS_MODULE=config.settings.prod` avec variables secrètes temporaires et `python manage.py check --deploy`: quatre avertissements de schéma OpenAPI, un pour le choix d'énumération partagé par les champs Tracker et trois pour les API MobilityMatch préexistantes sans serializer détectable. Aucun avertissement Django de sécurité n'a été émis. Cette commande valide les contrôles Django, pas un déploiement réel.
- `node --check` sur `tracker.js`, `heatmap.js` et le Service Worker: réussi.
- `git diff --check`: réussi.
- Couverture métier avec tests et migrations exclus:

```powershell
python -m coverage erase
python -m coverage run --source=tracker,carbon_service --omit='*/tests.py,*/migrations/*,tracker/admin.py,tracker/apps.py,tracker/urls.py' manage.py test tracker carbon_service
python -m coverage report -m
```

  Résultat réel après ajout des tests API : **90% global** (922 instructions), **100% carbon_service**, GPS **100%**, anti-triche **91%**, routage **96%**, classification **91%**, API **86%**, vues Django **80%**. Le seuil global de 85% est atteint pour ce périmètre métier; les vues et API demeurent les principales marges d'amélioration.

Les tests Tracker/carbone comprennent les tests API DRF d'authentification, CRUD, confidentialité propriétaire, idempotence et finalisation. Les tests navigateur/accessibilité, PostgreSQL/PostGIS, routage réel, données IA, Celery/Redis et déploiement n'ont pas été démontrés.

Pendant la suite complète, les tests préexistants de MobilityMatch ont reçu plusieurs réponses HTTP 403 du service ORS; ils ont géré ce repli et la suite est restée verte. Les appels ORS du tracker sont mockés dans ses tests et ne transmettent aucune position réelle.

## Validation de la préparation Render

- `python manage.py test`: **96 tests réussis** après ajout du support `DATABASE_URL` et de WhiteNoise.
- `python manage.py check --deploy` avec des valeurs d'environnement temporaires: aucun avertissement de sécurité Django; les quatre avertissements drf-spectacular déjà connus subsistent.
- `python manage.py collectstatic --noinput`: **199 fichiers copiés et 579 post-traités** avec le stockage manifest WhiteNoise.
- `python manage.py makemigrations --check --dry-run`: aucune migration manquante.

Ces contrôles valident la configuration et la collecte des statiques, pas la connectivité à une base Render réelle. Aucun service Render, Redis multi-instance ni worker Celery n'a été provisionné.
