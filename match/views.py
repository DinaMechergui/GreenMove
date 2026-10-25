"""
Vues pour l'application MobilityMatch AI.
Comprend la recherche avec IA de scoring, création de trajets, carte Leaflet, HTMX et API REST.
"""
from datetime import datetime, timedelta
import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import (
    Ride, RideBooking, Review, ChatRoom, ChatMessage,
    TrackingLink, SOSAlert, RideGroup,
)
from .forms import RideCreationForm, RideSearchForm, BookingForm, ReviewForm, SplitCalculatorForm
from .serializers import RideSerializer, RideBookingSerializer
from .services.geocoding import geocode_address
from .services.routing import get_route_details
from .services.ai_matcher import find_best_matches, compute_ride_match_score
from .services.similarity import ride_similarity
from .services.isochrones import find_meeting_point
from .services.clusters import cluster_recurring_rides, join_group
from .services.costs import compute_duo_split, compute_custom_split
from .services import telegram as telegram_service
from accounts.signals import ADMIN_GROUP


class IsRideOwnerOrAdminOrReadOnly(permissions.BasePermission):
    """Les trajets restent publics en lecture, seuls leur auteur et l'admin les modifient."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user.is_authenticated and
            (obj.user_id == request.user.pk or request.user.is_superuser or
             request.user.groups.filter(name=ADMIN_GROUP).exists())
        )


def search_rides(request):
    """
    Recherche intelligente de covoiturages avec calcul du score IA de correspondance.
    """
    form = RideSearchForm(request.GET or None)
    rides_qs = Ride.objects.filter(
        status=Ride.StatusChoices.ACTIVE,
        departure_datetime__gte=timezone.now() - timezone.timedelta(hours=2)
    ).select_related('user').order_by('departure_datetime')

    origin_query = request.GET.get('origin', '').strip()
    dest_query = request.GET.get('destination', '').strip()
    ride_type = request.GET.get('ride_type', '')
    only_green = request.GET.get('only_green_vehicles') == 'on'

    if ride_type:
        rides_qs = rides_qs.filter(ride_type=ride_type)

    if only_green:
        rides_qs = rides_qs.filter(user__vehicle_type__in=['ELECTRIC', 'HYBRID'])

    matched_results = []
    origin_coords = None
    dest_coords = None
    query_user = request.user if request.user.is_authenticated else None

    if origin_query or dest_query:
        if origin_query:
            origin_coords = geocode_address(origin_query)
        if dest_query:
            dest_coords = geocode_address(dest_query)

        # Si un point de départ ou d'arrivée est reconnu, on applique le moteur IA
        if origin_coords or dest_coords:
            ref_origin = origin_coords or (36.8000, 10.1800)
            ref_dest = dest_coords or (36.8392, 10.2447)
            # Vrai tracé routier de la recherche (ORS > OSRM > repli interne)
            query_route = get_route_details(ref_origin[0], ref_origin[1], ref_dest[0], ref_dest[1])
            query_polyline = query_route.get('coordinates') or None
            matched_results = find_best_matches(
                ref_origin,
                ref_dest,
                timezone.now(),
                rides_qs,
                limit=20,
                query_user=query_user,
                query_polyline=query_polyline,
            )

    # Si pas de recherche spécifique ou aucun résultat IA filtré, on affiche les trajets avec analyse par défaut
    if not matched_results:
        default_origin = (36.8000, 10.1800)
        default_dest = (36.8392, 10.2447)
        for ride in rides_qs[:20]:
            analysis = compute_ride_match_score(
                default_origin, default_dest, None, ride, query_user=query_user
            )
            matched_results.append({
                "ride": ride,
                "analysis": analysis,
                "score": analysis["match_percentage"]
            })

    # Préparation des données cartographiques JSON pour Leaflet
    map_rides = []
    for item in matched_results:
        r = item['ride']
        # Vrai tracé routier (échantillonné pour limiter la taille du JSON)
        route = list(r.polyline_coords)
        if len(route) > 150:
            step = len(route) // 150
            route = route[::step] + [route[-1]]
        map_rides.append({
            'id': r.id,
            'user': r.user.get_full_name() or r.user.username,
            'origin': r.origin_address,
            'origin_lat': r.origin_lat,
            'origin_lon': r.origin_lon,
            'destination': r.destination_address,
            'destination_lat': r.destination_lat,
            'destination_lon': r.destination_lon,
            'departure': r.departure_datetime.strftime('%d/%m %H:%M'),
            'price': float(r.price_tnd),
            'seats': r.seats_available,
            'score': item['score'],
            'overlap': item['analysis']['similarity']['overlap_pct'],
            'vehicle': r.user.get_vehicle_type_display(),
            'route': route if len(route) >= 2 else [],
        })

    context = {
        'form': form,
        'results': matched_results,
        'map_rides_json': json.dumps(map_rides),
        'origin_query': origin_query,
        'dest_query': dest_query,
    }

    # Si requête HTMX, on renvoie uniquement la liste des cartes de résultats
    if request.htmx:
        return render(request, 'match/includes/ride_list.html', context)

    return render(request, 'match/search.html', context)


@login_required
def create_ride(request):
    """
    Publication d'un nouveau trajet avec géocodage automatique des adresses.
    """
    if request.method == 'POST':
        form = RideCreationForm(request.POST)
        dep_time_str = request.POST.get('departure_time_input', '08:00')

        if form.is_valid():
            ride = form.save(commit=False)
            ride.user = request.user

            # Géocodage de l'adresse de départ
            coords_orig = geocode_address(ride.origin_address)
            ride.origin_lat, ride.origin_lon = coords_orig if coords_orig else (36.8000, 10.1800)

            # Géocodage de l'adresse d'arrivée
            coords_dest = geocode_address(ride.destination_address)
            ride.destination_lat, ride.destination_lon = coords_dest if coords_dest else (36.8392, 10.2447)

            # Assemblage de la date et heure de départ
            dep_date = form.cleaned_data['departure_date']
            try:
                time_parts = [int(p) for p in dep_time_str.split(':')]
                ride.departure_datetime = timezone.make_aware(
                    datetime.combine(dep_date, datetime.min.time().replace(hour=time_parts[0], minute=time_parts[1]))
                )
            except Exception:
                ride.departure_datetime = timezone.now() + timezone.timedelta(hours=2)

            ride.save()

            # Enregistrement du tracé routier réel (base du calcul de similarité)
            route_details = get_route_details(
                ride.origin_lat, ride.origin_lon,
                ride.destination_lat, ride.destination_lon
            )
            if route_details.get('coordinates'):
                ride.route_polyline = json.dumps(route_details['coordinates'])
                ride.save(update_fields=['route_polyline'])

            # Attribution de 30 GreenPoints pour publication d'un trajet vert
            request.user.eco_points += 30
            request.user.save(update_fields=['eco_points'])

            # Diffusion en temps réel via Channels si disponible
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        'public_ride_updates',
                        {
                            'type': 'ride_broadcast',
                            'message': {
                                'type': 'new_ride',
                                'id': ride.id,
                                'origin': ride.origin_address,
                                'destination': ride.destination_address,
                                'driver': request.user.username,
                            }
                        }
                    )
            except Exception:
                pass

            messages.success(request, "Votre trajet écologique a été publié ! Vous avez gagné 30 GreenPoints.")
            return redirect('match:ride_detail', pk=ride.id)
    else:
        # Pré-remplissage avec les adresses du profil si disponibles
        initial = {}
        if request.user.home_address:
            initial['origin_address'] = request.user.home_address
        if request.user.work_address:
            initial['destination_address'] = request.user.work_address
        form = RideCreationForm(initial=initial)

    return render(request, 'match/create_ride.html', {'form': form})


def ride_detail(request, pk: int):
    """
    Page de détails d'un trajet avec calcul d'itinéraire (ORS/OSRM) et carte Leaflet.
    """
    ride = get_object_or_404(Ride.objects.select_related('user'), pk=pk)
    booking_form = BookingForm()

    # Récupération de l'itinéraire tracé
    route_details = get_route_details(
        ride.origin_lat, ride.origin_lon,
        ride.destination_lat, ride.destination_lon
    )

    # Vérification si l'utilisateur connecté a déjà réservé ce trajet
    has_booked = False
    existing_booking = None
    if request.user.is_authenticated:
        existing_booking = RideBooking.objects.filter(
            ride=ride, passenger=request.user,
            status__in=(RideBooking.StatusChoices.PENDING, RideBooking.StatusChoices.ACCEPTED),
        ).first()
        has_booked = existing_booking is not None

    # Salon de chat du trajet
    room = ChatRoom.objects.filter(ride=ride).first()

    # Lien de suivi live partagé (le plus récent encore valide)
    active_link = (
        TrackingLink.objects.filter(ride=ride, is_active=True)
        .order_by('-created_at').first()
    )

    # Avis du conducteur & possibilité d'en laisser un
    driver_reviews = (
        Review.objects.filter(reviewed_user=ride.user)
        .select_related('reviewer').order_by('-created_at')[:5]
    )
    can_review = False
    if request.user.is_authenticated and request.user != ride.user:
        has_booking = RideBooking.objects.filter(
            ride=ride, passenger=request.user, status=RideBooking.StatusChoices.ACCEPTED
        ).exists()
        already_reviewed = Review.objects.filter(ride=ride, reviewer=request.user).exists()
        can_review = has_booking and not already_reviewed

    # Calculateur duo (frais + CO2)
    duo_split = compute_duo_split(ride)

    context = {
        'ride': ride,
        'booking_form': booking_form,
        'route_details': route_details,
        'route_coords_json': json.dumps(route_details.get('coordinates', [])),
        'has_booked': has_booked,
        'existing_booking': existing_booking,
        'chat_room': room,
        'active_link': active_link,
        'live_url': (
            request.build_absolute_uri(reverse('match:live_tracking', kwargs={'token': active_link.token}))
            if active_link else ''
        ),
        'driver_reviews': driver_reviews,
        'can_review': can_review,
        'review_form': ReviewForm(),
        'duo_split': duo_split,
    }
    return render(request, 'match/ride_detail.html', context)


@login_required
@require_POST
def book_ride(request, pk: int):
    """
    Création d'une réservation pour un trajet (support HTMX).
    """
    ride = get_object_or_404(Ride, pk=pk)

    if ride.status != Ride.StatusChoices.ACTIVE or ride.seats_available < 1:
        messages.warning(request, "Ce trajet n'accepte plus de réservations.")
        return redirect('match:ride_detail', pk=pk)

    if ride.user == request.user:
        messages.warning(request, "Vous ne pouvez pas réserver votre propre trajet.")
        return redirect('match:ride_detail', pk=pk)

    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            seats_requested = form.cleaned_data['seats_requested']
            if seats_requested > ride.seats_available:
                messages.error(request, "Le nombre de places demandé dépasse les places disponibles.")
                return redirect('match:ride_detail', pk=pk)
            booking, created = RideBooking.objects.get_or_create(
                ride=ride,
                passenger=request.user,
                defaults={
                    'seats_requested': form.cleaned_data['seats_requested'],
                    'message': form.cleaned_data['message'],
                    'status': RideBooking.StatusChoices.PENDING,
                }
            )
            if not created and booking.status in (
                RideBooking.StatusChoices.REJECTED, RideBooking.StatusChoices.CANCELLED
            ):
                booking.seats_requested = seats_requested
                booking.message = form.cleaned_data['message']
                booking.status = RideBooking.StatusChoices.PENDING
                booking.save(update_fields=['seats_requested', 'message', 'status'])
                created = True

            # Notification Telegram du conducteur (gratuite, no-op sans token)
            if created:
                telegram_service.notify_booking(booking)

            # Notification au conducteur via WebSocket si Channels est actif
            try:
                channel_layer = get_channel_layer()
                if channel_layer and created:
                    async_to_sync(channel_layer.group_send)(
                        f'user_notifications_{ride.user_id}',
                        {
                            'type': 'match_notification',
                            'message': {
                                'title': 'Demande de réservation reçue',
                                'text': f"{request.user.get_full_name() or request.user.username} a réservé {booking.seats_requested} place(s).",
                                'ride_id': ride.id
                            }
                        }
                    )
            except Exception:
                pass

            if request.htmx:
                return render(request, 'match/includes/booking_success.html', {'booking': booking})

            messages.success(request, "Votre demande a été envoyée au conducteur.")
            return redirect('match:ride_detail', pk=pk)

    return redirect('match:ride_detail', pk=pk)


@login_required
@require_POST
def manage_booking(request, booking_id: int):
    """Transitions contrôlées : conducteur accepte/refuse, passager annule."""
    action = request.POST.get('action')
    with transaction.atomic():
        booking = get_object_or_404(
            RideBooking.objects.select_for_update().select_related('ride', 'passenger'), pk=booking_id
        )
        ride = Ride.objects.select_for_update().get(pk=booking.ride_id)
        if action in ('accept', 'reject'):
            if request.user.pk != ride.user_id or booking.status != RideBooking.StatusChoices.PENDING:
                messages.error(request, "Cette demande ne peut pas être modifiée par ce compte.")
                return redirect('match:my_rides')
            if action == 'accept':
                if ride.status != Ride.StatusChoices.ACTIVE or ride.seats_available < booking.seats_requested:
                    messages.error(request, "Il n'y a pas assez de places disponibles.")
                    return redirect('match:my_rides')
                booking.status = RideBooking.StatusChoices.ACCEPTED
                ride.seats_available -= booking.seats_requested
                if ride.seats_available == 0:
                    ride.status = Ride.StatusChoices.FULL
                ride.save(update_fields=['seats_available', 'status', 'updated_at'])
                room, _ = ChatRoom.objects.get_or_create(ride=ride)
                room.participants.add(ride.user, booking.passenger)
                booking.passenger.eco_points += 20
                booking.passenger.save(update_fields=['eco_points'])
                messages.success(request, "Demande acceptée. Le chat est maintenant accessible aux participants.")
            else:
                booking.status = RideBooking.StatusChoices.REJECTED
                messages.success(request, "Demande refusée.")
        elif action == 'cancel':
            if request.user.pk != booking.passenger_id or booking.status not in (
                RideBooking.StatusChoices.PENDING, RideBooking.StatusChoices.ACCEPTED
            ):
                messages.error(request, "Cette réservation ne peut pas être annulée par ce compte.")
                return redirect('match:my_rides')
            if booking.status == RideBooking.StatusChoices.ACCEPTED:
                ride.seats_available += booking.seats_requested
                if ride.status == Ride.StatusChoices.FULL:
                    ride.status = Ride.StatusChoices.ACTIVE
                ride.save(update_fields=['seats_available', 'status', 'updated_at'])
                room = ChatRoom.objects.filter(ride=ride).first()
                if room:
                    room.participants.remove(booking.passenger)
            booking.status = RideBooking.StatusChoices.CANCELLED
            messages.success(request, "Réservation annulée.")
        else:
            messages.error(request, "Action de réservation invalide.")
            return redirect('match:my_rides')
        booking.save(update_fields=['status'])
    return redirect('match:my_rides')


@login_required
def my_rides(request):
    """
    Tableau de bord personnel : mes trajets proposés et mes réservations.
    """
    user = request.user
    proposed_rides = Ride.objects.filter(user=user).order_by('-departure_datetime')
    bookings = RideBooking.objects.filter(passenger=user).select_related('ride', 'ride__user').order_by('-created_at')

    context = {
        'proposed_rides': proposed_rides,
        'bookings': bookings,
        'incoming_bookings': RideBooking.objects.filter(ride__user=user).select_related(
            'ride', 'passenger'
        ).order_by('-created_at'),
    }
    return render(request, 'match/my_rides.html', context)


# ==========================================
# VUES API REST MOBILITYMATCH
# ==========================================

class APIRideListCreateView(generics.ListCreateAPIView):
    """Endpoint REST pour lister et créer des trajets."""
    queryset = Ride.objects.all().order_by('-departure_datetime')
    serializer_class = RideSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class APIRideDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD d'un trajet ; les mutations sont limitées au propriétaire ou à l'admin."""
    queryset = Ride.objects.select_related('user')
    serializer_class = RideSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsRideOwnerOrAdminOrReadOnly]


class APIFindMatchesView(APIView):
    """
    Endpoint REST d'IA pour trouver les trajets les plus compatibles
    selon les coordonnées ou adresses de départ et arrivée.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        origin = request.data.get('origin')
        destination = request.data.get('destination')

        if not origin or not destination:
            return Response(
                {"error": "Veuillez fournir 'origin' et 'destination'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        orig_coords = geocode_address(origin) or (36.8000, 10.1800)
        dest_coords = geocode_address(destination) or (36.8392, 10.2447)

        rides = Ride.objects.filter(status=Ride.StatusChoices.ACTIVE)
        query_user = request.user if getattr(request.user, 'is_authenticated', False) else None
        matches = find_best_matches(
            orig_coords, dest_coords, timezone.now(), rides, limit=10, query_user=query_user
        )

        data = []
        for m in matches:
            r = m['ride']
            data.append({
                'ride_id': r.id,
                'origin': r.origin_address,
                'destination': r.destination_address,
                'departure': r.departure_datetime,
                'seats_available': r.seats_available,
                'price_tnd': float(r.price_tnd),
                'match_percentage': m['score'],
                'breakdown': m['analysis']['breakdown'],
                'similarity': m['analysis']['similarity'],
                'ai_verdict': m['analysis']['ai_verdict'],
                'co2_saved_estimated': m['analysis']['co2_saved_estimated'],
            })

        return Response({"matches": data})


# ==========================================
# POINT DE RDV OPTIMAL (ISOCHRONES)
# ==========================================

def _extract_meeting_inputs(request_data):
    """Extrait les paires de coordonnées et la durée d'une requête."""
    data = request_data
    minutes = int(data.get('minutes', 15) or 15)
    minutes = max(5, min(60, minutes))

    ride_a = data.get('ride_a')
    ride_b = data.get('ride_b')
    if ride_a and ride_b:
        try:
            ra = Ride.objects.get(pk=int(ride_a))
            rb = Ride.objects.get(pk=int(ride_b))
            return (ra.origin_lat, ra.origin_lon), (rb.origin_lat, rb.origin_lon), minutes
        except (Ride.DoesNotExist, ValueError, TypeError):
            pass

    def _pair(prefix):
        try:
            return float(data.get(f'{prefix}lat')), float(data.get(f'{prefix}lon'))
        except (TypeError, ValueError):
            return None

    a = _pair('a') or _pair('origin_')
    b = _pair('b') or _pair('dest_')
    if a and b:
        return a, b, minutes
    return None


def meeting_point(request):
    """
    Page « Point de rendez-vous optimal » : intersection des isochrones
    OpenRouteService des deux utilisateurs.
    """
    origin_a = origin_b = None
    ride_a = ride_b = None

    # Sélection par trajets existants
    if request.GET.get('ride_a') and request.GET.get('ride_b'):
        ride_a = Ride.objects.filter(pk=request.GET['ride_a']).first()
        ride_b = Ride.objects.filter(pk=request.GET['ride_b']).first()
        if ride_a and ride_b:
            origin_a = (ride_a.origin_lat, ride_a.origin_lon)
            origin_b = (ride_b.origin_lat, ride_b.origin_lon)

    # Ou par coordonnées libres
    if origin_a is None:
        coords = _extract_meeting_inputs(request.GET)
        if coords:
            origin_a, origin_b, _ = coords

    # Défaut : deux quartiers de Tunis
    if origin_a is None:
        origin_a = (36.8782, 10.3247)   # La Marsa
        origin_b = (36.8392, 10.2447)   # Lac 2

    minutes = int(request.GET.get('minutes', 15) or 15)
    result = find_meeting_point(origin_a, origin_b, minutes=max(5, min(60, minutes)))

    active_rides = Ride.objects.filter(status=Ride.StatusChoices.ACTIVE).order_by(
        'departure_datetime'
    )[:40]

    context = {
        'result': result,
        'result_json': json.dumps(result),
        'origin_a': origin_a,
        'origin_b': origin_b,
        'minutes': max(5, min(60, minutes)),
        'ride_a': ride_a,
        'ride_b': ride_b,
        'active_rides': active_rides,
    }
    return render(request, 'match/meeting_point.html', context)


# ==========================================
# GROUPES DE TRAJECTOIRES RÉCURRENTS (DBSCAN)
# ==========================================

def trip_groups(request):
    """
    Groupes de trajets récurrents issue du clustering DBSCAN
    (covoiturage, pédibus, convois vélo).
    """
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.warning(request, "Connectez-vous pour rejoindre un groupe.")
            return redirect('accounts:login')
        ride_ids = [int(x) for x in request.POST.getlist('ride_ids') if str(x).isdigit()]
        previous = RideGroup.objects.filter(members=request.user).first()
        group = join_group(ride_ids, request.user)
        if group:
            if previous and previous.pk != group.pk:
                messages.info(
                    request,
                    f"Vous avez quitté le groupe « {previous.label} » : "
                    f"un seul groupe à la fois est autorisé."
                )
            messages.success(
                request,
                f"Vous avez rejoint le groupe « {group.label} » ({group.get_mode_display()})."
            )
        else:
            messages.error(request, "Groupe introuvable.")
        return redirect('match:groups')

    clusters = cluster_recurring_rides()
    mode_labels = {
        'COVOITURAGE': 'Covoiturage',
        'PEDIBUS': 'Pédibus',
        'CONVOI_VELO': 'Convoi vélo',
    }
    joined_ride_ids = set()
    current_group = None
    if request.user.is_authenticated:
        current_group = RideGroup.objects.filter(members=request.user).first()
        joined_ride_ids = set(
            RideGroup.objects.filter(members=request.user)
            .values_list('rides__id', flat=True)
        )

    for c in clusters:
        c['joined'] = any(r.id in joined_ride_ids for r in c['rides'])
        c['member_count'] = len({r.user_id for r in c['rides']})
        c['mode_display'] = mode_labels.get(c['mode'], c['mode'])

    context = {
        'clusters': clusters,
        'total_groups': len(clusters),
        'current_group': current_group,
    }
    return render(request, 'match/groups.html', context)


# ==========================================
# CHAT TEMPS RÉEL
# ==========================================

WELCOME_SUGGESTIONS = [
    "Bonjour ! Je serai à l'heure au point de rendez-vous. 👋",
    "On partage le trajet, merci pour la planète ! 🌱",
    "Je vous rejoins au lieu de départ indiqué, à tout de suite !",
]


@login_required
def chat_room(request, pk: int):
    """
    Chat temps réel d'un trajet (WebSocket) avec messages d'accueil suggérés.
    """
    ride = get_object_or_404(Ride.objects.select_related('user'), pk=pk)
    is_owner = request.user.pk == ride.user_id
    is_accepted_passenger = ride.bookings.filter(
        passenger=request.user, status=RideBooking.StatusChoices.ACCEPTED
    ).exists()
    if not (is_owner or is_accepted_passenger):
        messages.warning(
            request,
            "Le chat est réservé au conducteur et aux passagers dont la demande a été acceptée."
        )
        return redirect('match:ride_detail', pk=ride.id)

    room, _ = ChatRoom.objects.get_or_create(ride=ride)
    room.participants.add(ride.user)
    if is_accepted_passenger:
        room.participants.add(request.user)

    # Messages d'accueil suggérés (injectés une seule fois)
    if not room.messages.filter(is_suggestion=True).exists():
        ChatMessage.objects.bulk_create([
            ChatMessage(room=room, sender=None, content=text, is_suggestion=True)
            for text in WELCOME_SUGGESTIONS
        ])

    suggestions = list(
        room.messages.filter(is_suggestion=True, sender=None)
        .order_by('created_at').values_list('content', flat=True)
    )

    context = {
        'ride': ride,
        'room': room,
        'suggestions': suggestions,
        'other_participant': room.participants.exclude(pk=request.user.pk).first(),
    }
    return render(request, 'match/chat.html', context)


# ==========================================
# CALCULATEUR DE FRAIS & CO2 PAR DUO
# ==========================================

def split_calculator(request):
    """
    Calculateur de partage des frais et du CO₂ économisé par duo.
    Gère le rendu HTMX partiels via ?partial=1.
    """
    result = None
    form = SplitCalculatorForm(request.GET or None)

    if request.method == 'POST':
        form = SplitCalculatorForm(request.POST)
        if form.is_valid():
            ride = form.cleaned_data.get('ride')
            distance = form.cleaned_data.get('distance_km')
            passengers = form.cleaned_data.get('passengers') or 2
            total_cost = form.cleaned_data.get('total_cost')
            if ride is not None:
                result = compute_duo_split(
                    ride,
                    distance_km=distance if distance else None,
                    passenger_price=total_cost if total_cost else None,
                )
                result['ride'] = ride
                result['is_duo'] = True
            else:
                result = compute_custom_split(
                    distance_km=distance or 0,
                    passengers=passengers,
                    total_cost=total_cost,
                )
                result['is_duo'] = False
    elif form.is_bound and form.is_valid():
        ride = form.cleaned_data.get('ride')
        distance = form.cleaned_data.get('distance_km')
        if ride is not None:
            result = compute_duo_split(ride, distance_km=distance if distance else None)
            result['ride'] = ride
            result['is_duo'] = True

    context = {
        'form': form,
        'result': result,
        'result_json': json.dumps(result, default=str) if result else 'null',
    }
    if request.GET.get('partial') or request.headers.get('HX-Request'):
        return render(request, 'match/includes/split_result.html', context)
    return render(request, 'match/split.html', context)


# ==========================================
# SÉCURITÉ : SUIVI LIVE, SOS, AVIS
# ==========================================

@login_required
def create_tracking_link(request, pk: int):
    """
    Génère (ou réutilise) un lien de suivi live partagé pour un trajet.
    """
    ride = get_object_or_404(Ride, pk=pk)
    if ride.user != request.user:
        messages.error(request, "Seul le conducteur peut partager son suivi live.")
        return redirect('match:ride_detail', pk=pk)

    if request.method == 'POST':
        link = (
            TrackingLink.objects.filter(ride=ride, owner=request.user, is_active=True)
            .order_by('-created_at').first()
        )
        if link is None or not link.is_valid:
            link = TrackingLink.objects.create(
                ride=ride,
                owner=request.user,
                token=uuid.uuid4(),
                expires_at=timezone.now() + timedelta(hours=24),
            )
        messages.success(request, "Lien de suivi live créé (valable 24h).")
        return redirect('match:ride_detail', pk=pk)

    return redirect('match:ride_detail', pk=pk)


def live_tracking(request, token):
    """
    Page publique de suivi live (lecture seule pour les invités).
    """
    link = get_object_or_404(
        TrackingLink.objects.select_related('ride', 'owner'), token=token
    )
    is_owner = request.user.is_authenticated and request.user == link.owner
    is_valid = link.is_valid

    context = {
        'link': link,
        'ride': link.ride,
        'is_owner': is_owner,
        'is_valid': is_valid,
        'ws_token': str(link.token),
        'route_coords_json': json.dumps(link.ride.polyline_coords),
    }
    return render(request, 'match/live_tracking.html', context)


@login_required
def trigger_sos(request, pk: int):
    """
    Bouton SOS : crée une alerte, la diffuse aux participants du trajet (WS)
    et notifie Telegram si configuré.
    """
    ride = get_object_or_404(Ride, pk=pk)
    if request.method == 'POST':
        try:
            lat = float(request.POST.get('lat') or 0) or None
            lon = float(request.POST.get('lon') or 0) or None
        except (TypeError, ValueError):
            lat = lon = None

        alert = SOSAlert.objects.create(
            user=request.user,
            ride=ride,
            latitude=lat,
            longitude=lon,
            message=request.POST.get('message', ''),
        )

        payload = {
            'type': 'sos',
            'alert_id': alert.id,
            'user': request.user.get_full_name() or request.user.username,
            'ride_id': ride.id,
            'origin': ride.origin_address,
            'destination': ride.destination_address,
            'lat': lat,
            'lon': lon,
            'created_at': alert.created_at.strftime('%H:%M:%S'),
        }

        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'sos_alerts_{ride.id}', {'type': 'sos_alert', 'message': payload}
                )
                async_to_sync(channel_layer.group_send)(
                    f'user_notifications_{ride.user_id}',
                    {'type': 'match_notification', 'message': payload}
                )
        except Exception:
            pass

        telegram_service.notify_sos(alert)

        messages.error(
            request,
            "🆘 Alerte SOS envoyée aux participants du trajet. Appelez le 197 (Police) ou 190 (SAMU) si nécessaire."
        )
        return redirect('match:ride_detail', pk=pk)

    return redirect('match:ride_detail', pk=pk)


@login_required
def create_review(request, pk: int):
    """
    Avis post-trajet : note 1-5 → met à jour le score de fiabilité du profil.
    """
    ride = get_object_or_404(Ride.objects.select_related('user'), pk=pk)

    if request.method == 'POST':
        if request.user == ride.user:
            messages.warning(request, "Vous ne pouvez pas vous évaluer vous-même.")
            return redirect('match:ride_detail', pk=pk)

        booking = RideBooking.objects.filter(ride=ride, passenger=request.user).first()
        if booking is None:
            messages.warning(request, "Seuls les participants au trajet peuvent laisser un avis.")
            return redirect('match:ride_detail', pk=pk)

        form = ReviewForm(request.POST)
        if form.is_valid():
            review, created = Review.objects.get_or_create(
                ride=ride,
                reviewer=request.user,
                defaults={
                    'reviewed_user': ride.user,
                    'rating': form.cleaned_data['rating'],
                    'comment': form.cleaned_data.get('comment', ''),
                },
            )
            if created:
                request.user.eco_points += 15
                request.user.save(update_fields=['eco_points'])
                messages.success(
                    request,
                    f"Merci pour votre avis ! ({review.rating}/5) +15 GreenPoints."
                )
            else:
                messages.info(request, "Vous avez déjà laissé un avis pour ce trajet.")

    return redirect('match:my_rides')


# ==========================================
# API REST COMPLÉMENTAIRE
# ==========================================

class APIMeetingPointView(APIView):
    """Point de rendez-vous optimal (intersection des isochrones)."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        coords = _extract_meeting_inputs(request.data)
        if coords is None:
            return Response(
                {"error": "Fournissez 'ride_a'+'ride_b' ou 'alat'/'alon' et 'blat'/'blon'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        origin_a, origin_b, minutes = coords
        result = find_meeting_point(origin_a, origin_b, minutes=minutes)
        return Response(result)


class APIRideGroupsView(APIView):
    """Groupes DBSCAN des trajets récurrents."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            eps = float(request.query_params.get('eps', 1500))
            min_samples = int(request.query_params.get('min_samples', 2))
        except (TypeError, ValueError):
            return Response({"detail": "Paramètres eps/min_samples invalides."},
                            status=status.HTTP_400_BAD_REQUEST)
        clusters = cluster_recurring_rides(eps_m=eps, min_samples=min_samples)
        return Response({
            "groups": [
                {
                    "cluster_id": c['cluster_id'],
                    "label": c['label'],
                    "mode": c['mode'],
                    "origin": c['origin'],
                    "destination": c['destination'],
                    "avg_distance_km": c['avg_distance_km'],
                    "ride_ids": [r.id for r in c['rides']],
                    "total_members": c['total_members'],
                }
                for c in clusters
            ]
        })


# ==========================================
# MÉTRIQUES IA (Celery + polling HTMX)
# ==========================================

def _launch_ai_evaluation():
    """Lance la tâche Celery sans bloquer la requête si le broker est indisponible."""
    from django.core.cache import cache
    from .tasks import evaluate_ai_async, METRICS_STATUS_KEY
    cache.set(METRICS_STATUS_KEY, 'running', 600)
    try:
        evaluate_ai_async.delay()
        return True
    except Exception:
        cache.set(METRICS_STATUS_KEY, 'error', 600)
        return False


@login_required
def ai_metrics(request):
    """Page des métriques IA ; POST relance l'évaluation en arrière-plan."""
    from django.core.cache import cache
    from .tasks import METRICS_CACHE_KEY
    if request.method == 'POST' or cache.get(METRICS_CACHE_KEY) is None:
        _launch_ai_evaluation()
        if request.method == 'POST':
            return redirect('match:ai_metrics')
    return render(request, 'match/ai_metrics.html')


@login_required
def ai_metrics_status(request):
    """Fragment HTMX : « analyse en cours » (poll toutes les 2 s) puis résultats."""
    from django.core.cache import cache
    from .tasks import METRICS_CACHE_KEY, METRICS_STATUS_KEY
    status_value = cache.get(METRICS_STATUS_KEY, 'running')
    report = cache.get(METRICS_CACHE_KEY)
    if status_value == 'running' or (report is None and status_value != 'error'):
        status_value = 'running'
    return render(request, 'match/partials/ai_metrics_result.html',
                  {'status': status_value, 'report': report})
