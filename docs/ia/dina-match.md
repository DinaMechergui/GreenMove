# MobilityMatch AI — Dina

## Cas d'usage et mesure

MobilityMatch recommande des trajets compatibles en combinant proximité des départs et arrivées, horaire, préférences et fiabilité. Le rapport de matching compare le score multi-critères à une baseline « distance de départ seule » sur un jeu synthétique reproductible, explicitement déclaré comme tel. Il fournit précision, rappel, F1, exactitude, matrice de confusion et latence moyenne.

Le clustering DBSCAN des origines/destinations est comparé à une baseline de grille. Le rapport fournit silhouette, ARI face aux groupes attendus, nombre de groupes et durée. Les calculs de rapport passent par Celery; la page protégée `/match/ai/metrics/` expose l'état et le résultat.

## Références dans le code

- `match/services/ai_matcher.py` et `match/services/similarity.py` : score et similarité de trajets.
- `match/services/metrics.py` : génération du jeu synthétique, baseline, métriques de classification et clustering.
- `match/tasks.py` : calcul Celery, mise en cache, durée et état d'erreur.
- `match/consumers.py` : autorisation WebSocket du chat, vérifiée à la connexion et à l'envoi.
- `match/test_crud_compliance.py` : propriétaire/admin, transitions de réservation et disponibilité.

## Preuves à collecter pour la soutenance

1. Capturer le rapport F1/précision/rappel et la matrice de confusion face à la baseline, en indiquant que le jeu est synthétique.
2. Capturer silhouette et ARI DBSCAN face à la baseline de grille, puis la latence mesurée.
3. Montrer une demande en attente, l'acceptation/refus par le conducteur, la mise à jour du nombre de places et l'accès au chat uniquement après acceptation.
4. Enregistrer le rapport de couverture HTML et une capture des refus d'accès par URL directe et WebSocket.
5. Ajouter ici le notebook et les captures Lighthouse/axe lorsqu'ils auront été produits. Aucun score d'audit n'est présumé dans ce document.

## Reproduction

Les tests `match.test_ai` couvrent les métriques, la tâche asynchrone et les permissions de la page de rapport. Les tests CRUD de trajets sont dans `match.test_crud_compliance`. Les appels réseau externes doivent être simulés dans les tests pour garantir une exécution hors réseau.
