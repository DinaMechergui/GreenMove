# Évaluation IA — Mobility Tracker

## État constaté

Le jeu officiel **GeoLife Trajectories 1.3** de Microsoft a été téléchargé depuis la page Microsoft (archive ZIP de 313 164 406 octets), vérifié, puis extrait hors du dépôt dans `C:\Users\Admin\AppData\Local\GreenMove\datasets\geolife-extracted`. L'archive contient 182 utilisateurs, 18 670 fichiers de trajectoire et 69 utilisateurs avec `labels.txt`. Le modèle entraîné et son rapport sont conservés hors Git dans `C:\Users\Admin\AppData\Local\GreenMove\models\transport_geolife.joblib` et `transport_geolife.joblib.metrics.json`. La variable utilisateur Windows `TRANSPORT_MODEL_PATH` pointe vers cet artefact.

`tracker.services.transport_classifier.extract_features` calcule la vitesse moyenne et maximale, l'écart-type de vitesse, l'accélération absolue moyenne, le ratio d'arrêts, la précision GPS moyenne et le nombre de points. Le classifieur vérifie que l'artefact est LightGBM et que le nombre de caractéristiques correspond au schéma attendu.

## Entraînement et évaluation réels

Le modèle a été entraîné avec LightGBM 4.7.0. Le lecteur agrège les coordonnées ayant la même seconde, sépare les fichiers de trajectoire, ignore et compte les coordonnées invalides, et utilise uniquement les périodes explicitement annotées. Les fenêtres sont regroupées par utilisateur et la séparation est `GroupShuffleSplit` (25 % des utilisateurs en test, graine 42); aucune fenêtre d'un utilisateur de test n'entre dans l'entraînement.

Résultats réellement mesurés sur **213 545 fenêtres de 16 utilisateurs tenus à l'écart** (486 742 fenêtres d'entraînement de 48 autres utilisateurs) :

| Métrique | Résultat |
|---|---:|
| Accuracy | 0.6251 |
| Précision macro | 0.5212 |
| Recall macro | 0.5519 |
| F1 macro | 0.5084 |
| Latence d'inférence p50 / p95 (1 000 prédictions) | 12.02 / 48.32 ms |

| Mode | Précision | Recall | F1 | Support test |
|---|---:|---:|---:|---:|
| Vélo | 0.7391 | 0.6160 | 0.6719 | 49 182 |
| Bus | 0.5884 | 0.4253 | 0.4937 | 47 117 |
| Voiture / taxi | 0.3051 | 0.1780 | 0.2248 | 18 710 |
| Métro / subway | 0.1271 | 0.4244 | 0.1957 | 3 897 |
| Train | 0.8808 | 0.8080 | 0.8429 | 61 979 |
| Marche | 0.4865 | 0.8597 | 0.6214 | 32 660 |

La matrice de confusion (lignes = vrai, colonnes = prédit) est sauvegardée dans le rapport JSON accompagnant le modèle. Les classes `car` et `metro` ont une qualité trop faible pour être considérées comme des prédictions fiables; une piste sous le seuil de confiance est affichée comme **à confirmer** et n'alimente pas les segments ni le CO₂. Ces résultats Geolife ne démontrent pas la généralisation aux trajets du Grand Tunis : une validation locale étiquetée reste nécessaire.

La commande reproductible reste disponible :

```powershell
python manage.py train_transport_model --data-dir "C:\datasets\Geolife\Data" --output "C:\models\greenmove-transport.joblib"
```
