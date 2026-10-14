"""
Re-calcul des tracés routiers (route_polyline) manquants ou approximatifs.

Usage :
    python manage.py backfill_polylines              # trajets sans tracé réel
    python manage.py backfill_polylines --all        # tous les trajets (refresh)
    python manage.py backfill_polylines --min-overlap 25
"""
import json
import logging

from django.core.management.base import BaseCommand

from match.models import Ride
from match.services.routing import get_route_details

logger = logging.getLogger(__name__)

INTERNAL_SOURCE = "Moteur Interne Haversine"


class Command(BaseCommand):
    help = "Re-calcule les polylignes routières manquantes des trajets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Recalcule tous les trajets, pas seulement ceux sans tracé réel.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche le nombre de trajets à traiter sans rien modifier.",
        )

    def handle(self, *args, **options):
        qs = Ride.objects.exclude(status=Ride.StatusChoices.CANCELLED)
        if not options["all"]:
            # Tracé jugé manquant : vide, trop court ou repli "ligne droite" interne.
            ids = [
                ride.id for ride in qs.only("id", "route_polyline")
                if len(ride.polyline_coords) < 2
            ]
            qs = Ride.objects.filter(id__in=ids) if ids else Ride.objects.none()

        total = qs.count()
        self.stdout.write(self.style.WARNING(
            f"{total} trajet(s) à traiter ({'tous' if options['all'] else 'sans tracé réel'})."
        ))
        if options["dry_run"]:
            return

        ok = skipped = failed = 0
        for ride in qs.iterator(chunk_size=200):
            try:
                details = get_route_details(
                    ride.origin_lat, ride.origin_lon,
                    ride.destination_lat, ride.destination_lon,
                )
                coords = details.get("coordinates") or []
                if len(coords) < 2:
                    skipped += 1
                    continue
                # On n'enregistre que les tracés réels (routiers), pas le repli interne.
                if details.get("source") == INTERNAL_SOURCE:
                    skipped += 1
                    continue
                ride.route_polyline = json.dumps(coords)
                ride.save(update_fields=["route_polyline"])
                ok += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("Impossible de tracer le trajet %s: %s", ride.pk, exc)
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Terminé : {ok} tracé(s) enregistré(s), {skipped} ignoré(s), {failed} en échec."
        ))