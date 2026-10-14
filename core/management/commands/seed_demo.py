"""
Commande de gestion Django pour initialiser 20 utilisateurs et trajets de démonstration à Tunis.
Usage : python manage.py seed_demo
"""
from datetime import datetime, timedelta, time
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import CustomUser
from match.models import Ride, RideBooking

# Quartiers et zones clés du Grand Tunis avec coordonnées GPS réelles
TUNIS_LOCATIONS = [
    {"name": "Les Berges du Lac 2", "lat": 36.8392, "lon": 10.2447},
    {"name": "Ariana Centre", "lat": 36.8625, "lon": 10.1956},
    {"name": "La Marsa Corniche", "lat": 36.8782, "lon": 10.3247},
    {"name": "Le Bardo Centre", "lat": 36.8090, "lon": 10.1415},
    {"name": "Manouba Campus Universitaire", "lat": 36.8118, "lon": 10.0632},
    {"name": "Tunis Centre-ville (Av. Bourguiba)", "lat": 36.8000, "lon": 10.1800},
    {"name": "Ben Arous Zone Industrielle", "lat": 36.7531, "lon": 10.2189},
    {"name": "Carthage Amilcar", "lat": 36.8530, "lon": 10.3315},
    {"name": "Ennasr 2", "lat": 36.8710, "lon": 10.1580},
    {"name": "Mégrine Coteaux", "lat": 36.7680, "lon": 10.2310},
    {"name": "El Menzah 6", "lat": 36.8450, "lon": 10.1750},
    {"name": "Sidi Bou Saïd", "lat": 36.8700, "lon": 10.3420},
]

DEMO_USERS_DATA = [
    {
        "username": "yassine_lac",
        "first_name": "Yassine",
        "last_name": "Ben Ali",
        "email": "yassine.benali@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
        "vehicle_model": "Tesla Model 3 Blanche",
        "available_seats": 3,
        "eco_points": 780,
        "bio": "Ingénieur IA au Lac 2, passionné par la transition écologique et la tech propre.",
        "phone_number": "+216 98 123 456",
        "home": TUNIS_LOCATIONS[2],  # La Marsa
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(7, 45),
    },
    {
        "username": "mariem_eco",
        "first_name": "Mariem",
        "last_name": "Mansour",
        "email": "mariem.mansour@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.HYBRID,
        "vehicle_model": "Toyota Yaris Hybride Bleue",
        "available_seats": 3,
        "eco_points": 640,
        "bio": "Consultante RSE, covoitureuse convaincue depuis 2 ans sur l'axe Ariana - Centre-ville.",
        "phone_number": "+216 22 345 678",
        "home": TUNIS_LOCATIONS[1],  # Ariana
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 0),
    },
    {
        "username": "mehdi_manouba",
        "first_name": "Mehdi",
        "last_name": "Trabelsi",
        "email": "mehdi.trabelsi@greenmove.tn",
        "role": CustomUser.RoleChoices.BOTH,
        "vehicle_type": CustomUser.VehicleChoices.THERMAL_ECO,
        "vehicle_model": "Peugeot 208 PureTech Gris",
        "available_seats": 2,
        "eco_points": 420,
        "bio": "Enseignant-chercheur à l'Université de Manouba, alterne entre conduite et passager.",
        "phone_number": "+216 55 678 910",
        "home": TUNIS_LOCATIONS[3],  # Le Bardo
        "work": TUNIS_LOCATIONS[4],  # Manouba
        "dep_time": time(8, 15),
    },
    {
        "username": "salma_k",
        "first_name": "Salma",
        "last_name": "Khemir",
        "email": "salma.khemir@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.NONE,
        "vehicle_model": "",
        "available_seats": 0,
        "eco_points": 310,
        "bio": "Étudiante en informatique à ESPRIT (Ariana), cherche covoiturage depuis Ben Arous.",
        "phone_number": "+216 29 112 233",
        "home": TUNIS_LOCATIONS[6],  # Ben Arous
        "work": TUNIS_LOCATIONS[1],  # Ariana
        "dep_time": time(7, 30),
    },
    {
        "username": "aziz_jaziri",
        "first_name": "Aziz",
        "last_name": "Jaziri",
        "email": "aziz.jaziri@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
        "vehicle_model": "Nissan Leaf Verte",
        "available_seats": 3,
        "eco_points": 890,
        "bio": "Architecte éco-durable à Carthage, zéro émission sur tous mes trajets quotidiens.",
        "phone_number": "+216 50 445 566",
        "home": TUNIS_LOCATIONS[7],  # Carthage
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(8, 20),
    },
    {
        "username": "ines_bouazizi",
        "first_name": "Ines",
        "last_name": "Bouazizi",
        "email": "ines.bouazizi@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.BICYCLE_SCOOTER,
        "vehicle_model": "Trottinette électrique Xiaomi",
        "available_seats": 0,
        "eco_points": 520,
        "bio": "Designer UX, combine trottinette et covoiturage pour réduire l'empreinte carbone.",
        "phone_number": "+216 93 778 899",
        "home": TUNIS_LOCATIONS[8],  # Ennasr
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 10),
    },
    {
        "username": "mohamed_gharbi",
        "first_name": "Mohamed",
        "last_name": "Gharbi",
        "email": "mohamed.gharbi@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.HYBRID,
        "vehicle_model": "Hyundai Ioniq Hybride",
        "available_seats": 4,
        "eco_points": 570,
        "bio": "Directeur financier au Lac 2, trajets réguliers matin et soir depuis Le Bardo.",
        "phone_number": "+216 21 334 455",
        "home": TUNIS_LOCATIONS[3],  # Le Bardo
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(7, 50),
    },
    {
        "username": "nour_chaabane",
        "first_name": "Nour",
        "last_name": "Chaabane",
        "email": "nour.chaabane@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.NONE,
        "vehicle_model": "",
        "available_seats": 0,
        "eco_points": 280,
        "bio": "Analyste data à Mégrine, cherche un trajet matinal convivial et écologique.",
        "phone_number": "+216 97 556 677",
        "home": TUNIS_LOCATIONS[10], # Menzah 6
        "work": TUNIS_LOCATIONS[9],  # Mégrine
        "dep_time": time(8, 0),
    },
    {
        "username": "amine_dridi",
        "first_name": "Amine",
        "last_name": "Dridi",
        "email": "amine.dridi@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.THERMAL_ECO,
        "vehicle_model": "Renault Clio 5 TCe",
        "available_seats": 3,
        "eco_points": 390,
        "bio": "Développeur full-stack, navetteur quotidien Manouba ➔ Lac 2.",
        "phone_number": "+216 54 889 900",
        "home": TUNIS_LOCATIONS[4],  # Manouba
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(7, 40),
    },
    {
        "username": "farah_zaier",
        "first_name": "Farah",
        "last_name": "Zaier",
        "email": "farah.zaier@greenmove.tn",
        "role": CustomUser.RoleChoices.BOTH,
        "vehicle_type": CustomUser.VehicleChoices.HYBRID,
        "vehicle_model": "Renault Captur E-Tech",
        "available_seats": 3,
        "eco_points": 460,
        "bio": "Chef de projet événementiel, trajets fréquents entre La Marsa et Centre-ville.",
        "phone_number": "+216 26 223 344",
        "home": TUNIS_LOCATIONS[2],  # La Marsa
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 30),
    },
    {
        "username": "karim_sellami",
        "first_name": "Karim",
        "last_name": "Sellami",
        "email": "karim.sellami@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
        "vehicle_model": "MG ZS EV Électrique",
        "available_seats": 3,
        "eco_points": 820,
        "bio": "Médecin à Tunis, promoteur de l'air pur et de la réduction des particules fines.",
        "phone_number": "+216 99 667 788",
        "home": TUNIS_LOCATIONS[8],  # Ennasr
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(7, 30),
    },
    {
        "username": "chaima_ayari",
        "first_name": "Chaima",
        "last_name": "Ayari",
        "email": "chaima.ayari@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.NONE,
        "vehicle_model": "",
        "available_seats": 0,
        "eco_points": 340,
        "bio": "Avocate au Barreau de Tunis, recherche covoiturage fiable Bardo ➔ Palais de Justice.",
        "phone_number": "+216 23 889 911",
        "home": TUNIS_LOCATIONS[3],  # Le Bardo
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 15),
    },
    {
        "username": "hamza_riahi",
        "first_name": "Hamza",
        "last_name": "Riahi",
        "email": "hamza.riahi@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.HYBRID,
        "vehicle_model": "Kia Niro Hybride",
        "available_seats": 3,
        "eco_points": 590,
        "bio": "Manager logistique à Ben Arous, propose 3 places tous les jours ouvrés.",
        "phone_number": "+216 52 114 477",
        "home": TUNIS_LOCATIONS[1],  # Ariana
        "work": TUNIS_LOCATIONS[6],  # Ben Arous
        "dep_time": time(7, 20),
    },
    {
        "username": "sonia_bensalah",
        "first_name": "Sonia",
        "last_name": "Ben Salah",
        "email": "sonia.bensalah@greenmove.tn",
        "role": CustomUser.RoleChoices.BOTH,
        "vehicle_type": CustomUser.VehicleChoices.THERMAL_ECO,
        "vehicle_model": "Citroën C3 PureTech",
        "available_seats": 2,
        "eco_points": 380,
        "bio": "Responsable RH, aime partager la route pour papoter et dépenser moins de carburant.",
        "phone_number": "+216 94 336 699",
        "home": TUNIS_LOCATIONS[10], # Menzah 6
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(8, 5),
    },
    {
        "username": "omar_toumi",
        "first_name": "Omar",
        "last_name": "Toumi",
        "email": "omar.toumi@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.NONE,
        "vehicle_model": "",
        "available_seats": 0,
        "eco_points": 210,
        "bio": "Chercheur à l'Institut Pasteur, navetteur éco-citoyen.",
        "phone_number": "+216 28 774 411",
        "home": TUNIS_LOCATIONS[9],  # Mégrine
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 20),
    },
    {
        "username": "rym_belhadj",
        "first_name": "Rym",
        "last_name": "Belhadj",
        "email": "rym.belhadj@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
        "vehicle_model": "Fiat 500e Électrique",
        "available_seats": 2,
        "eco_points": 750,
        "bio": "Styliste et entrepreneure éthique à Sidi Bou Saïd, trajets vers le Centre.",
        "phone_number": "+216 58 996 633",
        "home": TUNIS_LOCATIONS[11], # Sidi Bou Saïd
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(9, 0),
    },
    {
        "username": "wael_hentati",
        "first_name": "Wael",
        "last_name": "Hentati",
        "email": "wael.hentati@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.HYBRID,
        "vehicle_model": "Toyota Corolla Hybride",
        "available_seats": 3,
        "eco_points": 610,
        "bio": "Consultant banque au Lac 2, trajet fluide et bonne musique garantis !",
        "phone_number": "+216 92 441 122",
        "home": TUNIS_LOCATIONS[6],  # Ben Arous
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(7, 45),
    },
    {
        "username": "linda_miled",
        "first_name": "Linda",
        "last_name": "Miled",
        "email": "linda.miled@greenmove.tn",
        "role": CustomUser.RoleChoices.PASSENGER,
        "vehicle_type": CustomUser.VehicleChoices.BICYCLE_SCOOTER,
        "vehicle_model": "Vélo pliant",
        "available_seats": 0,
        "eco_points": 490,
        "bio": "Journaliste environnementale, grande adepte de la multimodalité à Tunis.",
        "phone_number": "+216 27 663 355",
        "home": TUNIS_LOCATIONS[7],  # Carthage
        "work": TUNIS_LOCATIONS[5],  # Centre-ville
        "dep_time": time(8, 40),
    },
    {
        "username": "khaled_cherif",
        "first_name": "Khaled",
        "last_name": "Cherif",
        "email": "khaled.cherif@greenmove.tn",
        "role": CustomUser.RoleChoices.DRIVER,
        "vehicle_type": CustomUser.VehicleChoices.THERMAL_ECO,
        "vehicle_model": "Volkswagen Polo Eco",
        "available_seats": 3,
        "eco_points": 410,
        "bio": "Ingénieur télécoms, trajets réguliers Ariana - Lac 2 via voie express.",
        "phone_number": "+216 53 228 899",
        "home": TUNIS_LOCATIONS[1],  # Ariana
        "work": TUNIS_LOCATIONS[0],  # Lac 2
        "dep_time": time(8, 10),
    },
    {
        "username": "sarra_benamor",
        "first_name": "Sarra",
        "last_name": "Ben Amor",
        "email": "sarra.benamor@greenmove.tn",
        "role": CustomUser.RoleChoices.BOTH,
        "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
        "vehicle_model": "Renault Zoe Électrique",
        "available_seats": 3,
        "eco_points": 880,
        "bio": "Coordinatrice ONG Climat Tunis, milite pour un air sain et des villes apaisées.",
        "phone_number": "+216 95 119 988",
        "home": TUNIS_LOCATIONS[2],  # La Marsa
        "work": TUNIS_LOCATIONS[4],  # Manouba
        "dep_time": time(7, 30),
    },
]


class Command(BaseCommand):
    help = "Initialise 20 utilisateurs et des trajets réalistes dans le Grand Tunis pour la démonstration."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[INFO] Initialisation des donnees de demonstration GreenMove..."))

        # Création ou mise à jour de l'administrateur de test
        admin_user, created = CustomUser.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@greenmove.tn",
                "first_name": "Admin",
                "last_name": "GreenMove",
                "role": CustomUser.RoleChoices.BOTH,
                "vehicle_type": CustomUser.VehicleChoices.ELECTRIC,
                "vehicle_model": "Tesla Model Y",
                "available_seats": 4,
                "eco_points": 1500,
                "is_staff": True,
                "is_superuser": True,
                "home_address": "Tunis Centre-ville (Av. Bourguiba)",
                "home_lat": 36.8000,
                "home_lon": 10.1800,
                "work_address": "Les Berges du Lac 2",
                "work_lat": 36.8392,
                "work_lon": 10.2447,
            }
        )
        if created or not admin_user.check_password("admin123"):
            admin_user.set_password("admin123")
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("[OK] Compte superutilisateur pret : admin / admin123"))

        created_users = []
        # Création des 20 utilisateurs de démo
        for u_data in DEMO_USERS_DATA:
            user, u_created = CustomUser.objects.get_or_create(
                username=u_data["username"],
                defaults={
                    "first_name": u_data["first_name"],
                    "last_name": u_data["last_name"],
                    "email": u_data["email"],
                    "role": u_data["role"],
                    "vehicle_type": u_data["vehicle_type"],
                    "vehicle_model": u_data["vehicle_model"],
                    "available_seats": u_data["available_seats"],
                    "eco_points": u_data["eco_points"],
                    "bio": u_data["bio"],
                    "phone_number": u_data["phone_number"],
                    "home_address": u_data["home"]["name"],
                    "home_lat": u_data["home"]["lat"],
                    "home_lon": u_data["home"]["lon"],
                    "work_address": u_data["work"]["name"],
                    "work_lat": u_data["work"]["lat"],
                    "work_lon": u_data["work"]["lon"],
                    "departure_time_default": u_data["dep_time"],
                }
            )
            user.set_password("greenmove2026")
            user.save()
            created_users.append(user)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(created_users)} utilisateurs de demo initialises (mot de passe: greenmove2026)."))

        # Nettoyage des anciens trajets de test pour idempotence
        Ride.objects.all().delete()

        # Création de trajets réalistes pour aujourd'hui et les prochains jours
        now = timezone.now()
        base_date = now.replace(minute=0, second=0, microsecond=0)

        created_rides = []
        for i, user in enumerate(created_users):
            # Les conducteurs et les utilisateurs mixtes publient des offres
            if user.role in [CustomUser.RoleChoices.DRIVER, CustomUser.RoleChoices.BOTH]:
                # Trajet aller (Matin)
                day_offset = (i % 3)
                dep_time = user.departure_time_default or time(8, 0)
                dep_datetime = (base_date + timedelta(days=day_offset)).replace(
                    hour=dep_time.hour, minute=dep_time.minute
                )
                if dep_datetime < now:
                    dep_datetime += timedelta(days=1)

                ride_offer = Ride.objects.create(
                    user=user,
                    ride_type=Ride.RideTypeChoices.OFFER,
                    status=Ride.StatusChoices.ACTIVE,
                    origin_address=user.home_address,
                    origin_lat=user.home_lat or 36.8000,
                    origin_lon=user.home_lon or 10.1800,
                    destination_address=user.work_address,
                    destination_lat=user.work_lat or 36.8392,
                    destination_lon=user.work_lon or 10.2447,
                    departure_datetime=dep_datetime,
                    seats_available=user.available_seats if user.available_seats > 0 else 3,
                    price_tnd=random.choice([1.5, 2.0, 2.5, 3.0, 3.5]),
                    is_recurring=True,
                    recurring_days="Lun, Mar, Mer, Jeu, Ven",
                    description=f"Navette quotidienne {user.home_address} vers {user.work_address}. Climatisation douce, musique agreable, respect des horaires.",
                )
                created_rides.append(ride_offer)

                # Trajet retour (Soirée)
                ret_datetime = dep_datetime.replace(hour=17, minute=random.choice([30, 45, 15]))
                ride_return = Ride.objects.create(
                    user=user,
                    ride_type=Ride.RideTypeChoices.OFFER,
                    status=Ride.StatusChoices.ACTIVE,
                    origin_address=user.work_address,
                    origin_lat=user.work_lat or 36.8392,
                    origin_lon=user.work_lon or 10.2447,
                    destination_address=user.home_address,
                    destination_lat=user.home_lat or 36.8000,
                    destination_lon=user.home_lon or 10.1800,
                    departure_datetime=ret_datetime,
                    seats_available=user.available_seats if user.available_seats > 0 else 3,
                    price_tnd=ride_offer.price_tnd,
                    is_recurring=True,
                    recurring_days="Lun, Mar, Mer, Jeu, Ven",
                    description=f"Retour du travail {user.work_address} vers {user.home_address}.",
                )
                created_rides.append(ride_return)

            # Les passagers publient des demandes de trajets
            elif user.role == CustomUser.RoleChoices.PASSENGER:
                dep_time = user.departure_time_default or time(8, 0)
                dep_datetime = (base_date + timedelta(days=1)).replace(
                    hour=dep_time.hour, minute=dep_time.minute
                )
                req_ride = Ride.objects.create(
                    user=user,
                    ride_type=Ride.RideTypeChoices.REQUEST,
                    status=Ride.StatusChoices.ACTIVE,
                    origin_address=user.home_address,
                    origin_lat=user.home_lat or 36.8000,
                    origin_lon=user.home_lon or 10.1800,
                    destination_address=user.work_address,
                    destination_lat=user.work_lat or 36.8392,
                    destination_lon=user.work_lon or 10.2447,
                    departure_datetime=dep_datetime,
                    seats_available=1,
                    price_tnd=2.0,
                    is_recurring=True,
                    recurring_days="Lun, Mar, Mer, Jeu, Ven",
                    description=f"Recherche conducteur quotidien pour faire {user.home_address} vers {user.work_address}.",
                )
                created_rides.append(req_ride)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(created_rides)} trajets crees sur le Grand Tunis."))

        # Création de quelques réservations de démonstration
        passengers = [u for u in created_users if u.role == CustomUser.RoleChoices.PASSENGER]
        offer_rides = [r for r in created_rides if r.ride_type == Ride.RideTypeChoices.OFFER]

        if passengers and offer_rides:
            for p in passengers[:4]:
                ride_choice = random.choice(offer_rides)
                RideBooking.objects.create(
                    ride=ride_choice,
                    passenger=p,
                    status=RideBooking.StatusChoices.ACCEPTED,
                    seats_requested=1,
                    message="Bonjour ! Je serais ravi de partager le trajet avec vous chaque matin.",
                )
            self.stdout.write(self.style.SUCCESS("[OK] 4 reservations de demo acceptees creees."))

        self.stdout.write(self.style.SUCCESS("[SUCCES] Demonstration prete ! Lancez 'python manage.py runserver' pour tester."))
