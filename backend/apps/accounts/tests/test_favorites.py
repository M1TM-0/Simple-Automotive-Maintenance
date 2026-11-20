"""BE-062: oficinas favoritas do cliente."""

import pytest
from apps.accounts.models import Favorite
from apps.core.tests.factories import (
    AttendanceFactory,
    FavoriteFactory,
    PagWorkshopFactory,
    PointOfInterestFactory,
    deliver_attendance,
)
from apps.reviews.models import Review

URL = "/api/favorites/"


@pytest.mark.django_db
class TestFavorites:
    def test_post_is_idempotent(self, client_session, client_account):
        workshop = PagWorkshopFactory().workshop

        first = client_session.post(URL, {"id_workshop": workshop.pk}, format="json")
        second = client_session.post(URL, {"id_workshop": workshop.pk}, format="json")

        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"] == workshop.pk
        assert Favorite.objects.filter(client=client_account).count() == 1

    def test_list_item_shape_with_rating_and_type(self, client_session, client_account):
        point = PointOfInterestFactory(type="borracharia")
        page = PagWorkshopFactory(workshop__point_of_interest=point)
        workshop = page.workshop
        FavoriteFactory(client=client_account, workshop=workshop)
        for rating, status in ((4, "published"), (5, "published"), (1, "hidden")):
            budget, *_ = deliver_attendance(AttendanceFactory(workshop=workshop))
            Review.objects.create(budget=budget, rating=rating, status_review=status)

        body = client_session.get(URL).json()

        assert body["count"] == 1
        item = body["results"][0]
        assert item["id"] == item["id_workshop"] == workshop.pk
        assert item["name_fantasy"] == workshop.name_fantasy
        assert item["photo_profile"].endswith("/static/core/default-profile.png")
        assert (item["rating_avg"], item["rating_count"]) == (4.5, 2)
        assert item["type"] == "borracharia"

    def test_list_contains_only_own_favorites(self, client_session, client_account):
        mine = FavoriteFactory(client=client_account)
        FavoriteFactory()
        rows = client_session.get(URL).json()["results"]
        assert [row["id_favorite"] for row in rows] == [mine.pk]

    def test_delete_uses_workshop_id(self, client_session, client_account):
        favorite = FavoriteFactory(client=client_account)

        assert client_session.delete(f"{URL}{favorite.workshop_id}/").status_code == 204
        assert not Favorite.objects.filter(pk=favorite.pk).exists()

    def test_delete_not_favorited_is_404(self, client_session):
        other = FavoriteFactory()  # favorito de outro cliente
        assert client_session.delete(f"{URL}{other.workshop_id}/").status_code == 404
        assert Favorite.objects.filter(pk=other.pk).exists()

    @pytest.mark.parametrize("status", ["blocked", "inactive"])
    def test_unavailable_workshop_is_404(self, client_session, status):
        workshop = PagWorkshopFactory(workshop__status=status).workshop
        assert (
            client_session.post(
                URL, {"id_workshop": workshop.pk}, format="json"
            ).status_code
            == 404
        )

    def test_missing_workshop_is_404_and_bad_body_400(self, client_session):
        assert (
            client_session.post(URL, {"id_workshop": 999999}, format="json").status_code
            == 404
        )
        response = client_session.post(URL, {"id_workshop": "x"}, format="json")
        assert response.status_code == 400
        assert "id_workshop" in response.json()

    def test_access_matrix(self, api_client, workshop_session):
        assert api_client.get(URL).status_code == 401
        assert workshop_session.get(URL).status_code == 403
        assert (
            workshop_session.post(URL, {"id_workshop": 1}, format="json").status_code
            == 403
        )
