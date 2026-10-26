# 🌱 GreenMove - Plateforme Intelligente de Mobilité Durable

> **Hackathon Climat & IA 2026 — Grand Tunis**  
> Plateforme collaborative de mobilité urbaine décarbonée alimentée par l'intelligence artificielle, unissant covoiturage intelligent, suivi multimodal GPS, prédiction de trafic, budget carbone et gamification écologique.

---

## 📌 Présentation Générale

**GreenMove** répond aux enjeux de congestion et d'émissions de gaz à effet de serre dans le **Grand Tunis** (Tunis, Ariana, Ben Arous, La Marsa, Lac 2, Manouba, Le Bardo, Carthage). 

Le projet rassemble plusieurs briques technologiques interconnectées :
- **Intelligence Artificielle & Data** : Matching pondéré multi-critères, clustering DBSCAN de trajets réguliers, classification automatique de modes de transport (LightGBM) et prédiction du trafic.
- **Cartographie & Géodonnées Open Source** : Nominatim (OSM), OpenRouteService (ORS), OSRM et tuiles CartoDB Positron.
- **Expérience Utilisateur Moderne** : Interface sobre et écologique (thème soft inspiré de la nature), animations fluides, composants HTMX réactifs et support multilingue avec RTL (Français, Anglais, Arabe).

---

## 📦 Architecture des Modules & Fonctionnalités

### 1. 🏠 Core (`core`)
- **Vitrine & Présentation** : Page d'accueil moderne avec hero interactif, cartographie des pôles de mobilité de Tunis et statistiques d'impact.
- **Météo Temps Réel** : Intégration de l'API Open-Meteo pour adapter les recommandations aux conditions climatiques de Tunis.
- **Internationalisation (i18n)** : Support complet FR (défaut), EN et AR avec inversion dynamique du sens de lecture (`dir="rtl"`).

### 2. 👤 Comptes & Profil Éco (`accounts`)
- **Authentification & Sécurité** : Inscription/Connexion classique, OAuth Google (`django-allauth`), et tokens JWT pour l'API REST.
- **Profil Éco-citoyen** : Tableau de bord personnel, suivi des GreenPoints, badges éco et historique des gains de CO₂.
- **Préférences Utilisateur** : Gestion des affinités de trajet (fumeur/non-fumeur, musique, climatisation, préférences de genre).
- **Conformité RGPD** : Export complet des données personnelles (JSON) et droit à l'effacement définitif du compte.

### 3. 🚗 MobilityMatch IA (`match`)
- **Moteur de Matching IA** : Calcul de score de compatibilité pondéré (proximité géographique 45%, adéquation temporelle 25%, écologie du véhicule 20%, éco-points 10%).
- **Itinéraires & Cartographie** : Calcul d'itinéraires et tracés routiers réels avec Leaflet et OpenRouteService / OSRM.
- **Clustering DBSCAN** : Regroupement automatique des trajets récurrents domicile-travail pour suggérer des lignes de covoiturage, pédibus ou convois vélo.
- **Temps Réel & Sécurité** : Chat en direct par trajet (Django Channels / WebSockets), liens de partage de suivi live et bouton d'alerte SOS.
- **Outils Partagés** : Calculateur de partage de frais équitable et point de rencontre optimisé.

### 4. 📍 Eco-Tracker (`tracker`)
- **Enregistrement de Trajets GPS** : Suivi des déplacements avec chiffrement des coordonnées géographiques (Fernet / AES).
- **Classification Automatique de Transport (IA)** : Modèle de Machine Learning (LightGBM) identifiant le mode de transport utilisé (Marche, Vélo, Bus, Voiture, Métro).
- **Cartographie & Heatmap** : Visualisation cartographique détaillée et carte de chaleur des trajets enregistrés.
- **Bilan Carbone Automatique** : Calcul du CO₂ évité par rapport à un véhicule thermique individuel standard.
- **PWA & Offline** : Service Worker et manifeste pour fonctionnement hors-ligne, avec import/export de fichiers GPX.

### 5. 🚦 Traffic (`traffic`)
- **Surveillance du Trafic** : Carte interactive des points névralgiques de circulation dans le Grand Tunis.
- **Prédiction IA du Trafic** : Estimation des niveaux de congestion par plage horaire et suggestion de la "meilleure heure" de départ.
- **Historique & Analyses** : Suivi temporel des vitesses moyennes et des indices de fluidité.

### 6. 📅 Eco-Planner (`planner`)
- **Planificateur de Déplacements** : Organisation hebdomadaire des trajets réguliers domicile-travail.
- **Budget Carbone Mensuel** : Définition d'un plafond d'émissions avec jauge visuelle et alertes en cas de dépassement.
- **Calendrier & Synchronisation** : Export et import au format standard iCalendar (.ics).
- **Rapports d'Impact** : Génération de synthèses de mobilité téléchargeables en PDF, CSV et envoi par email.

### 7. 🎁 EcoRewards & Gamification (`rewards`)
- **Système de Récompenses** : Crédit automatique de GreenPoints à chaque trajet vert ou covoiturage réalisé.
- **Défis Écologiques** : Missions individuelles générées selon les habitudes et challenges collectifs inter-utilisateurs.
- **Classement (Leaderboard)** : Tableau des éco-citoyens les plus actifs de la communauté.
- **Boutique de Coupons Partenaires** : Échange de points contre des réductions auprès de partenaires locaux avec validation sécurisée par code / QR code.

### 8. 🌐 Services Transverses (`carbon_service` & `weather_service`)
- **`carbon_service`** : Moteur centralisé de calcul d'empreinte carbone basé sur les facteurs d'émission officiels (ADEME).
- **`weather_service`** : Service autonome fournissant les données météo et l'impact sur le choix modal.
- **Documentation OpenAPI / Swagger** : Spécification complète des API disponible sur `/api/docs/`.

---

## 🛠️ Stack Technique

- **Backend** : Python 3.11+, Django 5.x, Django REST Framework (DRF), SimpleJWT, Django Channels & Daphne (ASGI / WebSockets).
- **Base de données** : PostgreSQL 16 (production / dev Docker) ou SQLite (dev rapide).
- **Frontend** : Django Templates, HTMX, Bootstrap 5, Leaflet.js, CartoDB Positron, CountUp.js, AOS, Vanilla JavaScript.
- **Machine Learning & Data** : Scikit-Learn, LightGBM, Shapely, Pandas, NumPy.
- **APIs Externes Gratuites** : Nominatim OpenStreetMap (géocodage), OpenRouteService & OSRM (routage), Open-Meteo (météo sans clé).

---

## 🚀 Installation & Démarrage

### 1. Cloner le Dépôt
```bash
git clone https://github.com/DinaMechergui/GreenMove.git
cd GreenMove
```

### 2. Environnement Virtuel & Dépendances

#### Sur Windows (PowerShell) :
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Sur Linux / macOS :
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuration des Variables d'Environnement
Copiez le modèle d'environnement :
```bash
# Windows PowerShell
copy .env.example .env

# Linux / Mac
cp .env.example .env
```
> **Astuce** : Pour utiliser SQLite en local sans installer PostgreSQL, laissez ou indiquez `DB_ENGINE=sqlite` dans votre fichier `.env`.

### 4. Migrations & Initialisation de la Base
```bash
python manage.py migrate
```

### 5. Lancement du Serveur de Développement
```bash
python manage.py runserver
```
L'application est accessible à l'adresse : **http://127.0.0.1:8000/**  
La documentation de l'API Swagger : **http://127.0.0.1:8000/api/docs/**

---

## ⚡ Commandes de Démonstration & IA

Plusieurs commandes Django sur mesure permettent d'alimenter la plateforme avec des données réalistes pour tester immédiatement toutes les fonctionnalités :

| Commande | Rôle |
|---|---|
| `python manage.py seed_demo` | Crée l'administrateur (`admin`/`admin123`) et 20 utilisateurs réalistes du Grand Tunis avec trajets, avis et réservations |
| `python manage.py seed_planner` | Initialise des budgets carbone et des trajets réguliers pour le module Planner |
| `python manage.py seed_rewards` | Injecte les défis écologiques, badges et catalogue de récompenses du module Rewards |
| `python manage.py seed_traffic_points` | Initialise les points de surveillance du trafic sur les axes majeurs de Tunis |
| `python manage.py generate_synthetic_history` | Génère un jeu de données de trafic historique pour les entraînements IA |
| `python manage.py train_traffic_model` | Entraîne le modèle IA de prédiction de congestion routière |
| `python manage.py train_transport_model` | Entraîne le modèle de classification automatique des modes de déplacement (Tracker) |
| `python manage.py backfill_polylines` | Calcule et met en cache les tracés d'itinéraires Leaflet pour les trajets existants |

### Comptes de Démonstration
- **Super-administrateur** : identifiant `admin`, mot de passe `admin123`
- **Utilisateurs de démonstration** : mot de passe commun `greenmove2026`

---

## 🧪 Tests Unitaires & Vérification

Pour vérifier l'intégrité du projet et lancer la suite de tests :
```bash
python manage.py check
python manage.py test
```

---

## ☁️ Déploiement

- **Render** : Le projet inclut un fichier `render.yaml` et un script `build.sh` préconfigurés pour un déploiement avec serveur ASGI Daphne, WhiteNoise et base managée PostgreSQL.
- **Docker Compose** : Un fichier `compose.yaml` est fourni pour lancer rapidement la base PostgreSQL 16 en local :
  ```bash
  docker compose up -d db
  ```

---

## 👥 Équipe Projet
Projet conçu et développé dans le cadre du **Hackathon Climat & IA 2026**.  
Fait avec passion pour une Tunisie plus verte et durable 🇹🇳🌿
