# EcoPlanner — Yathreb

## Cas d'usage et mesure

EcoPlanner analyse les habitudes de déplacement et recommande un mode pour chaque trajet récurrent, en tenant compte du CO₂, du temps, du coût, du confort météo et d'un budget carbone hebdomadaire. `planner.services.planning.optimize_week` utilise OR-Tools CP-SAT lorsque disponible et expose le solveur de repli. Le résultat rapporte le CO₂ du plan, la baseline « mêmes trajets en voiture », le pourcentage économisé et le temps de calcul.

La typologie utilise KMeans sur trois variables normalisées : part voiture, part marche/vélo et kilomètres hebdomadaires. L'API de métriques expose le score silhouette, une baseline à règles fixes, la stabilité ARI sur cinq initialisations et l'inertie par nombre de clusters pour la courbe du coude. Si l'historique est insuffisant, l'API doit retourner `insufficient_data` plutôt que d'inventer un score.

## Références dans le code

- `planner/services/planning.py` : variables, optimisation, baseline voiture, durée de calcul.
- `planner/services/metrics.py` : silhouette, comparaison aux règles fixes, stabilité, inertie.
- `planner/tasks.py` : calcul plan + rendu PDF par Celery, état `queued/running/ready/error`.
- `planner/views.py` : endpoints personnels de génération, statut et téléchargement.

## Preuves à collecter pour la soutenance

1. Ouvrir `/planner/api/metrics/` avec un compte de démonstration ayant au moins trois profils avec historique et conserver la réponse JSON.
2. Montrer `solver`, durée et réduction CO₂ du plan face à la baseline voiture.
3. Générer le rapport depuis le tableau de bord et capturer l'état en cours puis prêt.
4. Enregistrer le rapport de couverture HTML et une capture du test de permissions par URL directe.
5. Ajouter ici le notebook et les captures d'audit Lighthouse/axe lorsqu'ils auront été produits. Aucun score d'audit n'est présumé dans ce document.

## Reproduction

Depuis la racine du dépôt, lancer les tests `planner` avec la base de test configurée. Pour les traitements asynchrones en production, le worker et le serveur web doivent partager Redis (`CACHE_URL`, qui prend le broker Redis comme valeur par défaut en configuration production).
