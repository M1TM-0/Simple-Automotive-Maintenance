from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def business_timezone():
    return ZoneInfo(settings.TIME_ZONE)


def business_now():
    return timezone.now().astimezone(business_timezone())


def to_business_time(moment):
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, UTC)
    return moment.astimezone(business_timezone())


def iso_weekday(moment=None):
    """1 = segunda ... 7 = domingo, no fuso do negócio (convenção de OPERATION_HOUR)."""
    moment = (
        to_business_time(moment) if isinstance(moment, datetime) else business_now()
    )
    return moment.isoweekday()
