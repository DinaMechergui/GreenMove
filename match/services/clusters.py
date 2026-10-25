"""
Groupes de trajets récurrents — clustering DBSCAN (MobilityMatch).
Regroupe les origines/destinations des trajets réguliers pour proposer
covoiturages, pédibus et convois vélo.
"""
import hashlib
import logging
import math
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _cluster_key(lat: float, lon: float) -> int:
    """Clé stable et compacte (max 7 hex → < 2^31) pour persister un cluster."""
    digest = hashlib.md5(f"{lat:.5f},{lon:.5f}".encode()).hexdigest()[:7]
    return int(digest, 16)


def _local_xy(lat: float, lon: float, lat0: float, lon0: float) -> List[float]:
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    return [(lon - lon0) * m_lon, (lat - lat0) * 111320.0]


def suggest_mode(rides: Sequence) -> str:
    """
    Suggère le mode de groupe selon les trajets membres :
    - vélos / trottinettes majoritaires → CONVOI_VELO
    - trajets courts (≤ 4 km) → PEDIBUS
    - sinon → COVOITURAGE
    """
    from ..models import RideGroup

    if not rides:
        return RideGroup.ModeChoices.COVOITURAGE

    bike_users = sum(
        1 for r in rides if getattr(r.user, 'vehicle_type', '') == 'BICYCLE_SCOOTER'
    )
    avg_distance = sum(r.distance_km for r in rides) / len(rides)

    if bike_users >= max(1, len(rides) // 2):
        return RideGroup.ModeChoices.CONVOI_VELO
    if avg_distance <= 4.0:
        return RideGroup.ModeChoices.PEDIBUS
    return RideGroup.ModeChoices.COVOITURAGE


def _short_label(text: str, max_len: int = 28) -> str:
    text = (text or '').strip()
    return text if len(text) <= max_len else text[: max_len - 1] + '…'


def cluster_recurring_rides(eps_m: float = 1500.0, min_samples: int = 2,
                            rides=None) -> List[Dict]:
    """
    DBSCAN sur [origin_lat, origin_lon, destination_lat, destination_lon]
    des trajets récurrents (ACTIFS).

    Returns:
        liste de clusters dict :
        {
          "cluster_id": int,          # -1 (bruit) exclu
          "rides": [Ride, ...],
          "label": str,
          "origin": (lat, lon),       # centroïde départ
          "destination": (lat, lon),  # centroïde arrivée
          "mode": "COVOITURAGE" | "PEDIBUS" | "CONVOI_VELO",
          "avg_distance_km": float,
          "total_members": int,       # places totales disponibles
        }
    """
    from sklearn.cluster import DBSCAN
    from ..models import Ride

    if rides is None:
        rides = list(
            Ride.objects.filter(is_recurring=True)
            .select_related('user')
            .order_by('departure_datetime')
        )
    else:
        rides = list(rides)

    if len(rides) < min_samples:
        return []

    lat0 = sum(r.origin_lat for r in rides) / len(rides)
    lon0 = sum(r.origin_lon for r in rides) / len(rides)

    # Features 4D normalisées en mètres (départ x,y + arrivée x,y)
    features = [
        _local_xy(r.origin_lat, r.origin_lon, lat0, lon0)
        + _local_xy(r.destination_lat, r.destination_lon, lat0, lon0)
        for r in rides
    ]

    # Sur-espacement des dimensions arrivée pour peser autant que le départ
    model = DBSCAN(eps=eps_m, min_samples=min_samples, metric='euclidean')
    labels = model.fit_predict(features)

    clusters: Dict[int, List] = {}
    for ride, label in zip(rides, labels):
        if label == -1:
            continue  # bruit : trajet isolé, pas de groupe proposé
        clusters.setdefault(int(label), []).append(ride)

    results = []
    for cluster_id, members in sorted(clusters.items()):
        n = len(members)
        origin = (
            sum(m.origin_lat for m in members) / n,
            sum(m.origin_lon for m in members) / n,
        )
        destination = (
            sum(m.destination_lat for m in members) / n,
            sum(m.destination_lon for m in members) / n,
        )
        avg_distance = sum(m.distance_km for m in members) / n
        label = f"{_short_label(members[0].origin_address)} → {_short_label(members[0].destination_address)}"
        results.append({
            'cluster_id': cluster_id,
            'rides': members,
            'label': label,
            'origin': origin,
            'destination': destination,
            'mode': suggest_mode(members),
            'avg_distance_km': round(avg_distance, 1),
            'total_members': sum(m.seats_available for m in members),
        })
    return results


def join_group(ride_ids: Sequence[int], user) -> Optional[object]:
    """
    Rejoint / crée le RideGroup correspondant à une liste de trajets.
    Un utilisateur ne peut appartenir qu'à un seul groupe à la fois :
    il est automatiquement retiré des autres groupes avant d'être ajouté.
    Retourne l'objet RideGroup créé ou mis à jour.
    """
    from ..models import Ride, RideGroup

    rides = list(Ride.objects.filter(id__in=ride_ids).select_related('user'))
    if not rides:
        return None

    lat0 = sum(r.origin_lat for r in rides) / len(rides)
    lon0 = sum(r.origin_lon for r in rides) / len(rides)
    cluster_key = _cluster_key(lat0, lon0)

    n = len(rides)
    group = RideGroup.objects.filter(cluster_id=cluster_key).first()
    if group is None:
        group = RideGroup.objects.create(
            cluster_id=cluster_key,
            mode=suggest_mode(rides),
            label=f"{_short_label(rides[0].origin_address)} → {_short_label(rides[0].destination_address)}",
            origin_lat=lat0,
            origin_lon=lon0,
            destination_lat=sum(r.destination_lat for r in rides) / n,
            destination_lon=sum(r.destination_lon for r in rides) / n,
        )
    group.rides.set(rides)

    # Un seul groupe par utilisateur : on le retire de tous les autres.
    for other in RideGroup.objects.filter(members=user).exclude(pk=group.pk):
        other.members.remove(user)

    group.members.add(user)
    return group


def _persist_clusters(clusters: List[Dict]) -> List:
    """
    Persiste les clusters en groupes (RideGroup) et applique l'adhésion
    automatique : chaque conducteur d'un trajet du cluster rejoint le groupe
    et quitte les autres groupes (règle « un seul groupe par utilisateur »).
    """
    from ..models import RideGroup

    groups = []
    for c in clusters:
        cluster_key = _cluster_key(c['origin'][0], c['origin'][1])
        group, _ = RideGroup.objects.update_or_create(
            cluster_id=cluster_key,
            defaults={
                'mode': c['mode'],
                'label': c['label'],
                'origin_lat': c['origin'][0],
                'origin_lon': c['origin'][1],
                'destination_lat': c['destination'][0],
                'destination_lon': c['destination'][1],
            },
        )
        group.rides.set(c['rides'])
        for owner in {r.user for r in c['rides']}:
            for other in RideGroup.objects.filter(members=owner).exclude(pk=group.pk):
                other.members.remove(owner)
            group.members.add(owner)
        groups.append(group)
    return groups


def sync_groups_with_rides(user=None, eps_m: float = 1500.0, min_samples: int = 2):
    """
    Adhésion automatique aux groupes DBSCAN.

    - Recalcule les clusters des trajets récurrents.
    - Le propriétaire d'un trajet du cluster rejoint automatiquement SON groupe
      (et quitte les autres) : quand une nouvelle personne publie un trajet
      similaire, elle rejoint le groupe sans action manuelle.
    - Si `user` est fourni, seuls ses clusters sont traités et son groupe
      (ou son groupe actuel) est retourné.
    """
    from ..models import RideGroup

    clusters = cluster_recurring_rides(eps_m=eps_m, min_samples=min_samples)
    if user is not None:
        clusters = [
            c for c in clusters
            if any(r.user_id == user.pk for r in c['rides'])
        ]

    groups = _persist_clusters(clusters)

    if user is None:
        return groups
    for group in groups:
        if group.members.filter(pk=user.pk).exists():
            return group
    return RideGroup.objects.filter(members=user).first()


def compute_and_persist_groups(eps_m: float = 1500.0, min_samples: int = 2) -> List[object]:
    """
    Recalcule les clusters, les persiste en base (cache dérivé) et y associe
    automatiquement leurs conducteurs. Les groupes orphelins sont supprimés.
    """
    from ..models import RideGroup

    clusters = cluster_recurring_rides(eps_m=eps_m, min_samples=min_samples)
    groups = _persist_clusters(clusters)
    RideGroup.objects.exclude(id__in=[g.pk for g in groups]).delete()
    return list(RideGroup.objects.filter(id__in=[g.pk for g in groups]))
