"""Leituras de avaliações reutilizadas por favoritos, perfil público e mapa.

DP-23: a nota média é calculada na consulta (sem coluna denormalizada) e só
considera avaliações `published` (RI-05).
"""

from apps.reviews.models import Review, ReviewStatus
from django.db.models import Avg, Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce


def rating_annotations(workshop_ref="pk"):
    """`{rating_avg, rating_count}` da oficina referenciada por `OuterRef(workshop_ref)`."""
    published = (
        Review.objects.filter(
            budget__workshop_id=OuterRef(workshop_ref),
            status_review=ReviewStatus.PUBLISHED,
        )
        .order_by()
        .values("budget__workshop_id")
    )
    return {
        "rating_avg": Subquery(
            published.annotate(value=Avg("rating")).values("value")[:1]
        ),
        "rating_count": Coalesce(
            Subquery(published.annotate(value=Count("id_review")).values("value")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
    }


def round_rating(value):
    return None if value is None else round(float(value), 1)
