"""
Commande de peuplement des badges, partenaires, récompenses et défis de démonstration
pour l'application EcoRewards (Grand Tunis).
Usage : python manage.py seed_rewards
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import CustomUser
from rewards.models import (
    Badge,
    RewardPartner,
    RewardItem,
    CollectiveChallenge,
    UserGamificationProfile,
    UserBadge,
    EcoTransaction,
)
from rewards.services.co2_calculator import get_or_create_gamification_profile
from rewards.services.kmeans_profiler import generate_personalized_challenges


class Command(BaseCommand):
    help = "Initialise les badges, partenaires éco, défis collectifs et profils de gamification."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[EcoRewards] Initialisation des donnees EcoRewards..."))

        # 1. Badges standards
        badges_data = [
            {
                'slug': 'premier-trajet',
                'name': 'Premier Trajet Éco',
                'description': 'A complété son tout premier covoiturage vert sur GreenMove.',
                'icon': 'bi-rocket-takeoff-fill',
                'badge_color': '#335C45',
                'category': Badge.CategoryChoices.RIDES,
                'threshold_type': Badge.ThresholdTypeChoices.RIDES_COUNT,
                'threshold_value': 1.0,
                'points_reward': 50,
            },
            {
                'slug': 'gardien-lac-2',
                'name': 'Gardien du Lac 2',
                'description': 'A évité plus de 10 kg de CO₂ sur les trajets autour du Lac de Tunis.',
                'icon': 'bi-water',
                'badge_color': '#0284C7',
                'category': Badge.CategoryChoices.CO2,
                'threshold_type': Badge.ThresholdTypeChoices.CO2_KG,
                'threshold_value': 10.0,
                'points_reward': 150,
            },
            {
                'slug': 'maestro-carbone-50kg',
                'name': 'Maestro Carbone (50 kg)',
                'description': 'A dépassé le palier impressionnant de 50 kg de CO₂ évités dans l\'atmosphère.',
                'icon': 'bi-tree-fill',
                'badge_color': '#52796F',
                'category': Badge.CategoryChoices.CO2,
                'threshold_type': Badge.ThresholdTypeChoices.CO2_KG,
                'threshold_value': 50.0,
                'points_reward': 300,
            },
            {
                'slug': 'serie-verte-7j',
                'name': 'Série Verte 7 Jours',
                'description': 'A covoituré 7 jours consécutifs aux heures de travail.',
                'icon': 'bi-fire',
                'badge_color': '#E9C46A',
                'category': Badge.CategoryChoices.STREAK,
                'threshold_type': Badge.ThresholdTypeChoices.STREAK_DAYS,
                'threshold_value': 7.0,
                'points_reward': 200,
            },
            {
                'slug': 'covoitureur-solidaire',
                'name': 'Covoitureur Solidaire',
                'description': 'A partagé son véhicule avec plus de 5 passagers différents.',
                'icon': 'bi-people-fill',
                'badge_color': '#84A98C',
                'category': Badge.CategoryChoices.COMMUNITY,
                'threshold_type': Badge.ThresholdTypeChoices.RIDES_COUNT,
                'threshold_value': 5.0,
                'points_reward': 180,
            },
            {
                'slug': 'champion-desengorgement',
                'name': 'Héros Anti-Bouchons',
                'description': 'A covoituré plus de 5 fois aux heures d\'affluence critique (7h-9h30).',
                'icon': 'bi-lightning-charge-fill',
                'badge_color': '#E76F51',
                'category': Badge.CategoryChoices.CHALLENGE,
                'threshold_type': Badge.ThresholdTypeChoices.RIDES_COUNT,
                'threshold_value': 5.0,
                'points_reward': 250,
            },
        ]

        created_badges = []
        for b_data in badges_data:
            b, created = Badge.objects.get_or_create(slug=b_data['slug'], defaults=b_data)
            created_badges.append(b)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(created_badges)} badges configures."))

        # 2. Partenaires réels du Grand Tunis
        partners_data = [
            {
                'name': 'Cosmitto Coffee Lac 2',
                'slug': 'cosmitto-lac-2',
                'category': RewardPartner.CategoryChoices.COFFEE_FOOD,
                'icon': 'bi-cup-hot-fill',
                'description': 'Café éthique et torréfaction artisanale au cœur des Berges du Lac 2.',
                'location_name': 'Rue de la Feuille d\'Érable, Les Berges du Lac 2',
                'latitude': 36.8392,
                'longitude': 10.2447,
                'validation_pin': '1001',
            },
            {
                'name': 'TotalEnergies Borne Électrique',
                'slug': 'totalenergies-borne',
                'category': RewardPartner.CategoryChoices.MOBILITY,
                'icon': 'bi-ev-station-fill',
                'description': 'Réseau de bornes de recharge rapide pour véhicules hybrides et 100% électriques.',
                'location_name': 'Station Lac 1, Berges du Lac, Tunis',
                'latitude': 36.8320,
                'longitude': 10.2280,
                'validation_pin': '2002',
            },
            {
                'name': 'Le Jardin Bio La Marsa',
                'slug': 'jardin-bio-marsa',
                'category': RewardPartner.CategoryChoices.COFFEE_FOOD,
                'icon': 'bi-basket3-fill',
                'description': 'Restaurant végétal et épicerie locale engagée pour le zéro déchet.',
                'location_name': 'Avenue Habib Bourguiba, La Marsa Corniche',
                'latitude': 36.8782,
                'longitude': 10.3247,
                'validation_pin': '3003',
            },
            {
                'name': 'E-Scooter Tunis Mobilité',
                'slug': 'e-scooter-tunis',
                'category': RewardPartner.CategoryChoices.MOBILITY,
                'icon': 'bi-scooter',
                'description': 'Location de trottinettes et vélos à assistance électrique urbains.',
                'location_name': 'Avenue Habib Bourguiba, Tunis Centre-ville',
                'latitude': 36.8000,
                'longitude': 10.1800,
                'validation_pin': '4004',
            },
        ]

        created_partners = {}
        for p_data in partners_data:
            p, _ = RewardPartner.objects.get_or_create(slug=p_data['slug'], defaults=p_data)
            created_partners[p.slug] = p

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(created_partners)} partenaires enregistres."))

        # 3. Articles Récompenses / Offres
        items_data = [
            {
                'partner': created_partners['cosmitto-lac-2'],
                'title': '1 Café Spécialité ou Boisson Fraîche Offerte',
                'description': 'Valable sur présentation du QR Code au comptoir Cosmitto Lac 2 du lundi au samedi.',
                'points_cost': 200,
                'discount_label': '1 Boisson Offerte',
                'stock': 100,
            },
            {
                'partner': created_partners['cosmitto-lac-2'],
                'title': '-25% sur l\'Addition Petit-Déjeuner Bio',
                'description': 'Remise immédiate sur toutes les formules brunch et petit-déjeuner éco-responsable.',
                'points_cost': 350,
                'discount_label': '-25% Brunch',
                'stock': 50,
            },
            {
                'partner': created_partners['totalenergies-borne'],
                'title': 'Session de Recharge Électrique Rapide (30 min)',
                'description': 'Crédit de recharge gratuite sur toutes les bornes 50kW TotalEnergies du Grand Tunis.',
                'points_cost': 450,
                'discount_label': '30 min Recharge Gratuite',
                'stock': 80,
            },
            {
                'partner': created_partners['jardin-bio-marsa'],
                'title': 'Panier Découverte Bio & Zéro Déchet',
                'description': 'Panier de fruits et légumes biologiques de saison issus des fermes de Mornag.',
                'points_cost': 600,
                'discount_label': 'Panier Bio Offert',
                'stock': 30,
            },
            {
                'partner': created_partners['e-scooter-tunis'],
                'title': '1 Heure de Balade en Trottinette Électrique',
                'description': 'Déverrouillage gratuit et 60 minutes de trajet libre dans le centre de Tunis ou La Marsa.',
                'points_cost': 280,
                'discount_label': '1H Trottinette Gratuite',
                'stock': 60,
            },
        ]

        for it in items_data:
            RewardItem.objects.get_or_create(
                partner=it['partner'],
                title=it['title'],
                defaults=it
            )

        self.stdout.write(self.style.SUCCESS("[OK] Offres et coupons partenaires crees."))

        # 4. Défis Collectifs Communautaires
        today = timezone.now().date()
        col_challenges_data = [
            {
                'title': 'Grand Tunis Zéro Émission : 5 000 kg de CO₂ Évités',
                'description': 'Objectif citoyen collectif pour dépolluer les axes routiers majeurs du Grand Tunis. Chaque kilomètre partagé alimente la jauge commune.',
                'scope': CollectiveChallenge.ScopeChoices.GLOBAL,
                'target_entity_name': 'Citoyens du Grand Tunis',
                'target_co2_kg': 5000.0,
                'current_co2_kg': 3420.0,
                'reward_description': 'Plantation de 100 arbres au Parc du Belvédère + Tirage au sort de 10 Pass Mobilité',
                'icon': 'bi-globe-americas',
                'start_date': today - timedelta(days=10),
                'end_date': today + timedelta(days=20),
                'is_active': True,
            },
            {
                'title': 'Challenge Universités Vertes : ESPRIT vs INSAT',
                'description': 'Compétition inter-campus d\'éco-mobilité étudiante et enseignante pour mutualiser les navettes quotidiennes vers Charguia et Centre Urbain Nord.',
                'scope': CollectiveChallenge.ScopeChoices.UNIVERSITY,
                'target_entity_name': 'ESPRIT vs INSAT',
                'target_co2_kg': 2000.0,
                'current_co2_kg': 1580.0,
                'reward_description': 'Installation d\'un abri vélo sécurisé avec station de réparation solaire sur le campus gagnant',
                'icon': 'bi-mortarboard-fill',
                'start_date': today - timedelta(days=5),
                'end_date': today + timedelta(days=15),
                'is_active': True,
            },
            {
                'title': 'Pôle Entreprises Lac 2 : Objectif Trafic Fluide',
                'description': 'Défi inter-entreprises pour désengorger l\'accès à la Rue du Lac de Constance et Avenue de la Bourse aux heures de pointe.',
                'scope': CollectiveChallenge.ScopeChoices.COMPANY,
                'target_entity_name': 'Zone d\'Affaires Lac 2',
                'target_co2_kg': 3000.0,
                'current_co2_kg': 1890.0,
                'reward_description': 'Trophée Mobilité Durable Hackathon 2026 remis à l\'entreprise la plus active',
                'icon': 'bi-building-check',
                'start_date': today - timedelta(days=7),
                'end_date': today + timedelta(days=21),
                'is_active': True,
            },
        ]

        for cc in col_challenges_data:
            CollectiveChallenge.objects.get_or_create(title=cc['title'], defaults=cc)

        self.stdout.write(self.style.SUCCESS("[OK] Defis collectifs avec jauges communautaires crees."))

        # 5. Mettre à jour tous les utilisateurs existants
        users = list(CustomUser.objects.all())
        districts_pool = ["Les Berges du Lac 2", "Ariana Centre", "La Marsa", "Tunis Centre-ville", "Le Bardo", "Ennasr 2", "El Menzah 6"]
        orgs_pool = ["ESPRIT", "INSAT", "Université de Tunis", "Telnet", "Vermeg", "Sofrecom"]

        for i, u in enumerate(users):
            prof = get_or_create_gamification_profile(u)
            prof.district = districts_pool[i % len(districts_pool)]
            prof.organization = orgs_pool[i % len(orgs_pool)]
            prof.total_co2_saved_kg = round(max(5.0, u.eco_points * 0.08), 1)
            prof.monthly_co2_saved_kg = round(prof.total_co2_saved_kg * 0.4, 1)
            prof.streak_days = max(1, (i % 7) + 1)
            prof.save()

            # Attribuer au moins 1 badge
            if created_badges:
                UserBadge.objects.get_or_create(user=u, badge=created_badges[0])
            if u.eco_points >= 400 and len(created_badges) > 1:
                UserBadge.objects.get_or_create(user=u, badge=created_badges[1])
            if u.eco_points >= 700 and len(created_badges) > 2:
                UserBadge.objects.get_or_create(user=u, badge=created_badges[2])

            # Générer les défis personnalisés
            generate_personalized_challenges(u, force_refresh=True)

        self.stdout.write(self.style.SUCCESS(f">> Profils et defis personnalises IA generes pour les {len(users)} utilisateurs."))
        self.stdout.write(self.style.SUCCESS(">> Base de donnees EcoRewards prete pour la demo !"))
