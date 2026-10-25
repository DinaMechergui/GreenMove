# Préparation à la soutenance — Roua

## Présentation des fonctionnalités réalisées

Le Mobility Tracker ajoute au projet Django existant un suivi de déplacements lié au `CustomUser`. Les vues utilisent l'authentification commune, n'interrogent que les trajets du propriétaire et bénéficient du middleware CSRF déjà activé. Les points de localisation sont chiffrés avec Fernet avant écriture dans la base; ils sont déchiffrés uniquement pour la carte privée et l'export du propriétaire.

Les principales entités sont `Trip` (état, dates, distance, durée, résultat éventuel d'IA, émissions et vérification), `GPSPoint` (numéro séquentiel et coordonnées chiffrées) et `TripSegment` (mode, distance, durée et CO₂e). Une clé de synchronisation identifie le démarrage d'un trajet et un index identifie chaque point, ce qui permet les répétitions réseau sans réinsérer le même point.

L'interface prend en charge le suivi GPS du navigateur, la liste paginée, les filtres, le détail carte, la correction manuelle, la suppression, le GPX et une comparaison carbone indicative. La capture nécessite une page active et une origine HTTPS ou localhost.

## Réponses aux questions possibles

1. **Quel est le rôle de Mobility Tracker ?**  
   Enregistrer les déplacements personnels et produire des éléments structurés (distance, durée, transport, CO₂e, contrôle) pour les autres services GreenMove.

2. **Pourquoi Django ?**  
   Le dépôt existant est un projet Django modulaire; le tracker réutilise son `CustomUser`, ses URLs, templates et middleware plutôt que de créer une application indépendante.

3. **Comment fonctionne le CRUD ?**  
   Les vues Django affichent les trajets du propriétaire, corrigent titre/mode et suppriment trajet et relations par cascade.

4. **Comment empêchez-vous l'accès au trajet d'un autre utilisateur ?**  
   Chaque vue de détail/requête recherche le trajet avec `user=request.user`. Un identifiant deviné donne une 404.

5. **La protection CSRF est-elle activée ?**  
   Oui, le middleware commun est activé; les formulaires POST incluent `{% csrf_token %}` et le point GPS exige le jeton de session.

6. **Pourquoi chiffrer les coordonnées ?**  
   Les déplacements sont des données personnelles sensibles. Le stockage garde uniquement des textes Fernet chiffrés; latitude/longitude ne sont pas des colonnes numériques persistantes.

7. **Où se trouve la clé ?**  
   Dans la variable `GPS_ENCRYPTION_KEY`, hors du dépôt. La clé doit être conservée et sauvegardée par l'environnement de déploiement; la perdre rend les anciens points indéchiffrables.

8. **Fernet protège-t-il contre toute attaque ?**  
   Non. Il chiffre les champs au repos, mais ne protège pas une application/clé compromise, un navigateur compromis ou l'exposition autorisée à un propriétaire.

9. **Comment calculez-vous la distance ?**  
   Par somme des distances haversine entre échantillons successifs, exprimée en kilomètres.

10. **Comment fonctionne LightGBM ?**  
    Le service prépare des caractéristiques de vitesse, accélération, arrêts, précision et nombre de points, puis charge un modèle configuré et renvoie sa classe et confiance. Aucun artefact livré actuellement.

11. **Quelles métriques IA avez-vous obtenues ?**  
    Aucune : le dépôt ne fournit pas le jeu Geolife annoté ni le modèle test. Il serait incorrect d'inventer accuracy, precision, recall, F1 ou matrice de confusion.

12. **Quelle est la différence entre entraînement et inférence ?**  
    L'entraînement ajuste et évalue le modèle hors ligne sur des données étiquetées; l'inférence prédit une classe pour un trajet enregistré. Seule l'interface d'inférence est présente.

13. **Pourquoi pas de Celery ?**  
    La configuration du projet ne déclare pas Celery ni worker Redis. Le module ne prétend pas offrir une exécution asynchrone; le raccordement doit suivre l'infrastructure commune.

14. **Quel est le rôle de Redis ?**  
    Aucune utilisation Redis propre au tracker n'a été mise en place. Le projet configure éventuellement Channels Redis, qui ne constitue pas à lui seul un worker Celery.

15. **Quel est le rôle d'OSRM ?**  
    Une fonction explicite peut envoyer une trace pour map-matching et restituer géométrie/confiance. Elle n'est pas appelée automatiquement afin de ne pas partager la trace privée à l'insu de l'utilisateur.

16. **Quel est le rôle d'Overpass ?**  
    La fonction de contexte retourne des éléments OSM (pistes cyclables et relations transport) pour contribuer à une analyse. Elle ne permet pas de conclure qu'un véhicule est un bus.

17. **Comment le CO₂ est-il calculé ?**  
    Distance en passager-km × facteur versionné en kg CO₂e/passager-km. Le service partagé documente facteur, source, arrondis et modes.

18. **Pourquoi marche/vélo sont-ils à zéro ?**  
    Le zéro représente les émissions directes du déplacement; il ne représente pas l'analyse de cycle de vie de l'alimentation, du vélo ou des infrastructures.

19. **Comment l'application marche hors-ligne ?**  
    Le service worker met en cache quelques ressources statiques et la file IndexedDB chiffre temporairement les points; retour en ligne, la page active renvoie les points avec idempotence serveur.

20. **La synchronisation fonctionne-t-elle en arrière-plan ?**  
    Non. Elle est relancée au retour de connexion tant que la page de trajet reste ouverte; Background Sync n'est pas annoncé.

21. **Comment importez-vous un GPX sans entités XML ?**  
    Le fichier est limité à 2 Mio et les déclarations DTD/ENTITY sont rejetées avant parsing; points, coordonnées et horodatages sont validés.

22. **Comment évitez-vous une fausse accusation de fraude avec un GPS imprécis ?**  
    La faible précision seule n'est pas un flag. Des vitesses impossibles, dates incohérentes ou points invalides sont expliqués par règles.

23. **Comment éviter les doubles récompenses ?**  
    Les UUID de trajet, identifiant idempotent et digest de trace offrent une base à un consommateur de rewards, mais aucune attribution n'est implémentée ici.

24. **Quelles sont les limites de la comparaison écologique ?**  
    La page compare la même distance avec des facteurs communs; elle n'est pas un itinéraire routé et ne calcule pas des temps de transport.

25. **Les autres modules consomment-ils déjà carbon_service ?**  
    Non; Planner et Rewards visibles sont encore des pages placeholders. L'interface partagée est créée, mais une intégration contractuelle nécessite leur implémentation.

26. **Quels tests sont requis avant livraison ?**  
    Installer les dépendances, exécuter `check`, migrations, tests tracker/carbon et coverage. Les valeurs de couverture doivent être celles d'une exécution réelle.

27. **Avez-vous testé PostgreSQL/PostGIS ?**  
    Non. Le dépôt configure SQLite par défaut et aucun service Postgres/PostGIS d'équipe n'est disponible dans l'environnement.

28. **Le service est-il déployé ?**  
    Non. Aucun serveur, secret ou plateforme de staging n'est disponible pour prouver un déploiement.

29. **Pourquoi la grille n'est-elle pas entièrement validée ?**  
    Les deux PDF demandés sont absents du dépôt; certaines ressources sont aussi absentes (données IA, clés, Postgres et services d'exécution).

30. **Quelle est l'étape suivante prioritaire ?**  
    Recevoir les PDF et les données Geolife autorisées, configurer les secrets et exécuter les tests sur la version intégrée à l'environnement de l'équipe.
