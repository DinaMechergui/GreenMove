# Évaluation IA — Mobility Tracker

## Résultat observé

Statut : **non évalué / modèle indisponible**. Le dépôt ne contient ni les données Geolife annotées requises, ni un modèle entraîné, ni un résultat d'évaluation reproductible. Aucune accuracy, precision, recall, F1-score, matrice de confusion ou latence n'est publiée car aucune évaluation réelle n'a pu être faite.

`predict_transport` renvoie explicitement `unavailable` quand `TRANSPORT_MODEL_PATH` est absent ou que LightGBM/joblib n'est pas disponible. Ce résultat n'est pas présenté comme une prédiction de transport.

## Composants présents

- `tracker.services.transport_classifier.extract_features`: caractéristiques de vitesse moyenne et maximale, écart-type des vitesses, accélération absolue moyenne, ratio d'arrêts (<1 km/h), précision GPS moyenne et nombre de points.
- `predict_transport`: charge un classifieur LightGBM sérialisé via joblib depuis `TRANSPORT_MODEL_PATH`, puis renvoie classe, confiance et temps d'inférence mesuré avec `perf_counter`.
- Un trajet trop court pour fournir trois points ne lance pas de classification.
- La commande d'entraînement, validation par utilisateur/trajectoire et la génération de rapport n'ont pas été implémentées.

## À fournir pour une évaluation reproductible

1. Une copie autorisée de Geolife avec les fichiers `labels.txt` et trajectoires réellement accessibles.
2. Une procédure de construction des fenêtres GPS et d'association des labels aux périodes.
3. Un découpage train/test groupé par utilisateur, afin d'éviter la fuite de trajectoires d'un même utilisateur.
4. Entraîner LightGBMClassifier sur le train uniquement, et sauvegarder le pipeline et la liste ordonnée de caractéristiques.
5. Évaluer les prédictions test avec accuracy, precision/recall/F1 par classe, matrice de confusion, support et latence d'inférence médiane/p95 avec le nombre d'observations.
6. Examiner bus/voiture et classes insuffisamment représentées. Ne pas présenter ces classes si les labels et supports ne les distinguent pas.

Les limites actuelles incluent l'absence de modèle, de normalisation temporelle documentée, de calibration de confiance, de jeux test tenus à l'écart et de mesures sur des trajets tunisiens.
