import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .context import current_precipitation, is_holiday
from .models import MonitoringPoint, TrafficSnapshot
from .services import TrafficAPIError, fetch_flow
from .synthetic import speeds, synthetic_congestion

logger = logging.getLogger(__name__)


@shared_task
def collect_traffic_snapshots():
    now = timezone.now()
    local = timezone.localtime(now)
    rain = current_precipitation()
    holiday = is_holiday(local.date())
    saved = 0

    for point in MonitoringPoint.objects.filter(is_active=True):
        if settings.TRAFFIC_SOURCE == 'tomtom':
            try:
                v = fetch_flow(point.latitude, point.longitude)
            except TrafficAPIError as exc:
                logger.warning('TomTom indisponible pour %s : %s', point.name, exc)
                continue
            cur, free, cong, source = v['current_speed'], v['free_flow_speed'], v['congestion'], 'tomtom'
        else:
            cong = synthetic_congestion(point.profile, local, rain, holiday)
            cur, free = speeds(point.profile, cong)
            source = 'synthetic'

        TrafficSnapshot.objects.create(
            point=point, timestamp=now, current_speed=cur, free_flow_speed=free,
            congestion=cong, precipitation_mm=rain, is_holiday=holiday, source=source,
        )
        saved += 1

    logger.info('%s snapshots enregistrés (%s)', saved, settings.TRAFFIC_SOURCE)
    return saved