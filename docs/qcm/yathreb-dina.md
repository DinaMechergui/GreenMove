# Banque QCM — Yathreb et Dina

Chaque question a une seule bonne réponse. Les réponses sont regroupées à la fin pour permettre une révision croisée.

## Yathreb — accounts et planner

1. Pourquoi filtrer un endpoint de trajets par `request.user` ?  
   A. Pour accélérer les migrations · B. Pour empêcher un utilisateur de lire/modifier les trajets d'un autre · C. Pour activer Celery

2. À quoi sert `annotate()` dans une requête Django ?  
   A. À ajouter des valeurs calculées à chaque ligne/groupement · B. À créer une migration · C. À vérifier le CSRF

3. Quelle baseline est utilisée pour l'économie CO₂ du plan EcoPlanner ?  
   A. Le trajet à vélo · B. La moyenne de tous les utilisateurs · C. Les mêmes trajets effectués en voiture

4. Que signifie un score silhouette proche de 1 ?  
   A. Les clusters sont mieux séparés et plus cohérents · B. Le modèle est toujours exact · C. Le temps de calcul est plus court

5. Que mesure l'ARI entre plusieurs exécutions KMeans ?  
   A. La stabilité des regroupements, indépendamment du nom des labels · B. Les émissions CO₂ · C. Le taux d'erreurs HTTP

6. Pourquoi tracer l'inertie pour plusieurs valeurs de k ?  
   A. Pour choisir une valeur de k au moyen de la méthode du coude · B. Pour choisir le port Redis · C. Pour calculer le rappel

7. Quel est le rôle d'OR-Tools dans le plan hebdomadaire ?  
   A. Résoudre le choix de modes sous contraintes et minimiser le score · B. Servir les pages Django · C. Chiffrer les mots de passe

8. Quel mécanisme protège les formulaires HTML Django contre les requêtes intersites ?  
   A. Le jeton CSRF · B. `select_related()` · C. La couverture de tests

9. Pourquoi un objet personnel doit-il être filtré dans `get_queryset()` d'une vue DRF ?  
   A. Pour appliquer l'isolation au niveau de la requête, y compris sur les URL directes · B. Pour forcer un tri alphabétique · C. Pour rendre l'API publique

10. Pourquoi exécuter le rendu PDF avec Celery ?  
    A. Pour ne pas bloquer la requête web pendant le calcul/rendu · B. Pour supprimer le besoin d'authentification · C. Pour remplacer les tests unitaires

## Dina — MobilityMatch AI

11. Que prend en compte le matching multi-critères par rapport à une baseline « distance seule » ?  
    A. L'origine et la destination, l'horaire et d'autres critères de compatibilité · B. Uniquement la couleur du véhicule · C. Seulement le nom du conducteur

12. Dans une classification binaire, que représente le rappel ?  
    A. La part des vrais cas positifs retrouvés par le modèle · B. La part des pages accessibles au clavier · C. La moyenne des latences

13. Pourquoi afficher la matrice de confusion avec le F1 ?  
    A. Pour voir les faux positifs et faux négatifs derrière le score agrégé · B. Pour prouver le déploiement · C. Pour remplacer le jeu de test

14. Que fait DBSCAN avec les points trop isolés ?  
    A. Il peut les marquer comme bruit (`-1`) · B. Il les convertit en utilisateurs admin · C. Il les supprime de la base

15. Que signifie l'ARI dans l'évaluation d'un clustering ?  
    A. L'accord entre clusters prédits et groupes de référence, corrigé du hasard · B. Le nombre de routes servies par minute · C. Le taux de réussite HTTP

16. Quel serveur est nécessaire pour exécuter Django Channels en WebSocket ?  
    A. Un serveur ASGI, par exemple Daphne ou Uvicorn · B. Uniquement un serveur WSGI standard · C. Un serveur SMTP

17. Quand un passager peut-il ouvrir le chat du trajet après le changement de workflow ?  
    A. Dès qu'il consulte la page · B. Après acceptation de sa demande par le conducteur · C. Après la création du compte, sans réservation

18. Pourquoi revérifier l'autorisation au moment d'enregistrer un message WebSocket ?  
    A. L'accès peut avoir changé depuis la connexion; l'envoi doit rester protégé · B. Pour améliorer le contraste · C. Pour recalculer le clustering

19. Pourquoi utiliser Celery pour les métriques IA ?  
    A. Pour exécuter le calcul hors de la requête HTTP et suivre son état · B. Pour remplacer PostgreSQL · C. Pour désactiver les permissions

20. Que faut-il préciser lors de la présentation des résultats synthétiques ?  
    A. Que le jeu est synthétique et reproductible, et ne constitue pas une validation terrain · B. Qu'il provient forcément de vrais utilisateurs · C. Qu'une bonne accuracy suffit à prouver l'absence de biais

## Réponses

1-B, 2-A, 3-C, 4-A, 5-A, 6-A, 7-A, 8-A, 9-A, 10-A, 11-A, 12-A, 13-A, 14-A, 15-A, 16-A, 17-B, 18-A, 19-A, 20-A.
