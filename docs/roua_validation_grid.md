# Traçabilité de validation — module Roua

Statuts utilisés: VALIDÉ = vérification réelle disponible; PARTIEL = fonctionnalité partielle ou validation incomplète; BLOQUÉ = dépendance externe/documentaire manquante; NON FAIT = absent.

| Critère | Exigence PDF | Fichier/fonction implémenté | Test | Résultat | Preuve |
|---|---|---|---|---|---|
| CRUD | Créer/lire/modifier/supprimer | `tracker.views`, `tracker.api_views`, `tracker.models.Trip` | Django Client et APIClient | VALIDÉ | Opérations web et REST testées; la conformité exacte à l'attribution reste bloquée par l'absence des PDF |
| Cohérence fonctionnelle | Fonctionnalités conformes à l'attribution PDF | PDF non présent | Aucun | BLOQUÉ | Aucun des deux PDF n'est présent dans le dépôt |
| Tests unitaires | Modèles, contraintes et services | `tracker/tests.py`, `carbon_service/tests.py` | Django TestCase | PARTIEL | 44 tests Tracker/carbone et 96 tests projet réussis; entraînement IA et intégrations d'autres membres restent absents |
| Tests d'intégration | Vues, auth, CRUD, erreurs | `tracker/tests.py` | Django Client, DRF APIClient | PARTIEL | 44 tests Tracker/carbone et 96 tests projet réussis; navigateur/PostGIS/worker non vérifiés |
| Couverture | Mesure réelle, cible 85% | `coverage` sur le code métier tracker/carbon | 44 tests ciblés | VALIDÉ | Rapport réel: 90% global (tests/migrations exclus), 100% carbon_service et gps_service; voir [roua_tests.md](./roua_tests.md) |
| Sécurité | CSRF, validation, secrets, fichiers | middleware commun, GPS Fernet, GPX limité | tests GPS/GPX et `check --deploy` | PARTIEL | Contrôles Django sans avertissement de sécurité; quatre avertissements OpenAPI, audit complet non effectué |
| Permissions | Propriétaire/administrateur côté serveur | filtres `user=request.user`, `login_required`, `IsTripOwner` | tests web et API | PARTIEL | Authentification et isolation du propriétaire testées; rôles spécifiques admin non ajoutés |
| Robustesse | erreurs et services externes | services GPS/GPX/OSRM | tests unitaires | PARTIEL | délais/erreurs OSRM présents; résilience production à auditer |
| HTML sémantique | Structure et labels | templates `tracker/` | aucun audit navigateur | PARTIEL | `main`, `header`, labels/table headers employés |
| Attributs ARIA | annonces et alternatives | `tracker/detail.html` | aucun axe/lecteur d'écran | PARTIEL | régions `status` et description de carte présentes |
| Contraste | WCAG AA | couleurs GreenMove existantes | axe/Lighthouse absent | NON FAIT | Ratio non mesuré |
| Clavier | Parcours clavier | contrôles HTML natifs | test navigateur absent | PARTIEL | Contrôles natifs et focus CSS |
| Pertinence IA | Transport automatique utile et justifié | `transport_classifier.py` | tests d'absence de modèle | PARTIEL | Pas de résultat IA inventé |
| Intégration IA | LightGBM au sein du module | `predict_transport` | test modèle indisponible | PARTIEL | Chargement configurable; artefact absent |
| UX IA | Chargement/résultat/échec/retry | détail trajet | aucun modèle async | PARTIEL | État d'indisponibilité explicite |
| Métriques IA | métriques test réelles | `docs/roua_ai_evaluation.md` | aucun dataset/model | BLOQUÉ | Geolife annoté et artefact non fournis |
| Performances | Latence, endpoint, p95 | chrono d'inférence interne | mesure charge absente | NON FAIT | Pas de mesure suffisante |
| Asynchronisme | Celery/Redis | Aucun worker tracker | aucun | NON FAIT | Seulement Channels est présent dans le projet |
| UX/UI responsive | Écrans tracker mobile | templates et `tracker.css` | test navigateur mobile absent | PARTIEL | Styles responsive, non audités visuellement |
| Git | Branche, commits, historique | branche `feature/roua-mobility-tracker` | `git status/log` | PARTIEL | Branche dédiée; modifications restent non commitées |
| Intégration | Contrats Planner/Rewards/autres | champs `Trip`, `carbon_service` | tests de contrat absents | PARTIEL | Modules Planner/Rewards actuels = placeholders |
| Déploiement | PostgreSQL, Redis, worker, HTTPS (guide Render) | `config.settings.prod`, WhiteNoise, `build.sh`, Daphne ASGI | `check --deploy`, collectstatic et tests ciblés | PARTIEL | Configuration Render préparée selon le guide; PostgreSQL/HTTPS réels non exercés; Redis multi-instance et worker Celery/IA toujours absents |
| Préparation soutenance | Explication fondée sur le code | `docs/roua_soutenance.md` | revue documentaire | PARTIEL | Limites réelles décrites; PDF de référence manquant |

## Critères complémentaires demandés dans le prompt

| Fonction | État | Preuve / limite |
|---|---|---|
| Chiffrement GPS au repos | PARTIEL | Fernet applicatif; tests réels inclus, variable `GPS_ENCRYPTION_KEY` à configurer en déploiement |
| GPX import/export | PARTIEL | Parseur borné, DTD/entités refusés et autorisation propriétaire; tests automatisés passés |
| Hors-ligne/PWA | PARTIEL | Service worker statique, queue IndexedDB chiffrée; capture exige page ouverte |
| Map matching / Overpass | PARTIEL | Services explicites et bornés; non appelés automatiquement, donc données privées par défaut |
| Heatmap | PARTIEL | Vue privée propriétaire, limitée à 2 000 points et visualisée en Leaflet. Audit de rendu mobile/accessibilité non exécuté |
| Segmentation multimodale persistée | PARTIEL | Service de fenêtres/lissage; persistance multimode et test complet non intégrés |
| Comparateur | PARTIEL | Calcul même-distance et estimations affichées comme non routées; pas de routage ORS |
