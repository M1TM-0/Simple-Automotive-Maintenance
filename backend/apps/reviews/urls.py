from apps.reviews.views import (
    DenunciationCreateView,
    PublicWorkshopReviewListView,
    ReviewCreateView,
    WorkshopReviewListView,
    WorkshopReviewResponseView,
)
from django.urls import path

urlpatterns = [
    path("reviews/", ReviewCreateView.as_view(), name="reviews"),
    path("denunciations/", DenunciationCreateView.as_view(), name="denunciations"),
    path(
        "workshops/<int:workshop_id>/reviews/",
        PublicWorkshopReviewListView.as_view(),
        name="public-workshop-reviews",
    ),
    path(
        "workshop/reviews/", WorkshopReviewListView.as_view(), name="workshop-reviews"
    ),
    path(
        "workshop/reviews/<uuid:pk>/response/",
        WorkshopReviewResponseView.as_view(),
        name="workshop-review-response",
    ),
]
