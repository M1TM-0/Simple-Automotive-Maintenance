"""BE-075 (Django Admin de contas) e BE-078 (desativação e anonimização, DP-18)."""

import logging

import pytest
from apps.accounts.models import Client, Favorite, Workshop
from apps.attendances.models import Attendance
from apps.core.tests.factories import (
    AttendanceFactory,
    ClientFactory,
    FavoriteFactory,
    NotificationFactory,
    PointOfInterestFactory,
    deliver_attendance,
    jpeg_upload,
    make_ready_workshop,
    make_review,
)
from apps.notifications.models import Notification
from apps.reviews.models import Review
from apps.workshops.models import PagWorkshop
from django.core.files.storage import default_storage
from django.test import Client as BrowserClient

pytestmark = pytest.mark.django_db

PASSWORD = "SenhaTeste123"
CLIENTS = "/admin/accounts/client/"
WORKSHOPS = "/admin/accounts/workshop/"


@pytest.fixture
def staff_browser(django_user_model):
    user = django_user_model.objects.create_superuser(
        "chefe", "chefe@exemplo.com", "SenhaAdmin123"
    )
    browser = BrowserClient()
    browser.force_login(user)
    return browser


def run_action(browser, changelist, action, *pks, **extra):
    return browser.post(
        changelist,
        {"action": action, "_selected_action": [str(pk) for pk in pks], **extra},
    )


def login(api, role, email, password=PASSWORD):
    return api.post(
        "/api/auth/login/",
        {"role": role, "email": email, "password": password},
        format="json",
    )


def map_ids(api):
    return {
        (item["kind"], item["id"])
        for item in api.get("/api/map/points/").json()["results"]
    }


# ------------------------------------------------------------------ acesso


class TestAccess:
    def test_non_staff_is_sent_to_the_admin_login(self, django_user_model):
        browser = BrowserClient()
        browser.force_login(
            django_user_model.objects.create_user("comum", "c@exemplo.com", "x" * 12)
        )

        response = browser.get(CLIENTS)

        assert response.status_code == 302 and "/admin/login/" in response["Location"]

    def test_staff_without_permission_gets_403(self, django_user_model):
        browser = BrowserClient()
        browser.force_login(
            django_user_model.objects.create_user(
                "mod", "m@exemplo.com", "x" * 12, is_staff=True
            )
        )

        assert browser.get(CLIENTS).status_code == 403

    def test_staff_with_permission_can_block(self, django_user_model, api_client):
        from django.contrib.auth.models import Permission

        user = django_user_model.objects.create_user(
            "mod", "m@exemplo.com", "x" * 12, is_staff=True
        )
        user.user_permissions.add(
            Permission.objects.get(codename="change_workshop"),
            Permission.objects.get(codename="view_workshop"),
        )
        browser = BrowserClient()
        browser.force_login(user)
        workshop = make_ready_workshop()

        assert (
            run_action(browser, WORKSHOPS, "block_accounts", workshop.pk).status_code
            == 302
        )
        workshop.refresh_from_db()
        assert workshop.status == "blocked"

    def test_no_add_and_no_delete(self, staff_browser):
        client = ClientFactory()

        assert staff_browser.get(f"{CLIENTS}add/").status_code == 403
        assert staff_browser.get(f"{CLIENTS}{client.pk}/delete/").status_code == 403
        assert staff_browser.get(f"{WORKSHOPS}add/").status_code == 403
        assert "delete_selected" not in staff_browser.get(CLIENTS).content.decode()
        assert Client.objects.filter(pk=client.pk).exists()

    def test_changelists_render_and_filter_by_status(self, staff_browser):
        ClientFactory(name="Ana Ativa")
        ClientFactory(name="Beto Bloqueado", status="blocked")
        make_ready_workshop()

        page = staff_browser.get(CLIENTS, {"status__exact": "blocked"}).content.decode()

        assert "Beto Bloqueado" in page and "Ana Ativa" not in page
        assert staff_browser.get(WORKSHOPS).status_code == 200


# --------------------------------------------------------------- formulário


class TestClientForm:
    def test_password_hash_is_not_in_the_form(self, staff_browser):
        client = ClientFactory()

        page = staff_browser.get(f"{CLIENTS}{client.pk}/change/").content.decode()

        assert 'name="password_hash"' not in page
        assert client.password_hash not in page
        assert 'name="email"' not in page  # só leitura

    def test_posting_password_hash_or_email_changes_nothing_but_the_name(
        self, staff_browser
    ):
        client = ClientFactory(name="Nome Antigo", email="original@exemplo.com")
        original_hash = client.password_hash

        response = staff_browser.post(
            f"{CLIENTS}{client.pk}/change/",
            {
                "name": "Nome Novo",
                "phone_number": "",
                "status": "active",
                "password_hash": "!forjado",
                "email": "outro@exemplo.com",
            },
        )

        assert response.status_code == 302
        client.refresh_from_db()
        assert (client.name, client.password_hash, client.email) == (
            "Nome Novo",
            original_hash,
            "original@exemplo.com",
        )

    def test_saving_does_not_overwrite_a_concurrent_password_change(
        self, staff_browser
    ):
        client = ClientFactory()
        staff_browser.get(f"{CLIENTS}{client.pk}/change/")
        Client.objects.filter(pk=client.pk).update(
            password_hash="hash-trocado-enquanto-o-form-estava-aberto"
        )

        staff_browser.post(
            f"{CLIENTS}{client.pk}/change/",
            {"name": "Outro", "phone_number": "", "status": "active"},
        )

        assert (
            Client.objects.get(pk=client.pk).password_hash
            == "hash-trocado-enquanto-o-form-estava-aberto"
        )

    def test_status_change_in_the_form_is_audited(self, staff_browser, caplog):
        client = ClientFactory()

        with caplog.at_level(logging.INFO, logger="sam.audit"):
            staff_browser.post(
                f"{CLIENTS}{client.pk}/change/",
                {"name": client.name, "phone_number": "", "status": "blocked"},
            )

        assert Client.objects.get(pk=client.pk).status == "blocked"
        [record] = [
            r
            for r in caplog.records
            if r.name == "sam.audit" and r.getMessage() == "admin.account.status"
        ]
        assert (
            record.target_type,
            record.target_id,
            record.from_status,
            record.to_status,
        ) == (
            "client",
            str(client.pk),
            "active",
            "blocked",
        )


# ---------------------------------------------------------- bloquear / ativar


class TestStatusActions:
    def test_blocked_workshop_cannot_login_loses_session_and_leaves_the_map(
        self, staff_browser, api_client, account_session
    ):
        workshop = make_ready_workshop()
        Workshop.objects.filter(pk=workshop.pk).update(
            point_of_interest=PointOfInterestFactory()
        )
        session = account_session(workshop, "workshop")
        assert ("workshop", workshop.pk) in map_ids(api_client)
        assert session.get("/api/auth/me/").status_code == 200

        response = run_action(staff_browser, WORKSHOPS, "block_accounts", workshop.pk)

        assert response.status_code == 302
        login_response = login(api_client, "workshop", workshop.email)
        assert login_response.status_code == 403
        assert login_response.json() == {
            "detail": "Conta bloqueada. Entre em contato com o suporte."
        }
        assert ("workshop", workshop.pk) not in map_ids(api_client)
        assert api_client.get(f"/api/workshops/{workshop.pk}/").status_code == 404
        assert session.get("/api/auth/me/").status_code == 401

    def test_reactivating_restores_login(self, staff_browser, api_client):
        client = ClientFactory(status="blocked")

        run_action(staff_browser, CLIENTS, "activate_accounts", client.pk)

        assert login(api_client, "client", client.email).status_code == 200

    def test_deactivated_client_login_is_403(self, staff_browser, api_client):
        """BE-078: `inactive` → login 403, dados e histórico preservados."""
        client = ClientFactory()
        AttendanceFactory(client=client)

        run_action(staff_browser, CLIENTS, "deactivate_accounts", client.pk)

        response = login(api_client, "client", client.email)
        assert response.status_code == 403
        assert response.json() == {
            "detail": "Conta desativada. Entre em contato com o suporte."
        }
        client.refresh_from_db()
        assert client.status == "inactive" and client.name.startswith("Cliente")
        assert Attendance.objects.filter(client=client).count() == 1

    def test_bulk_action_is_audited_once_per_changed_account(
        self, staff_browser, caplog
    ):
        changed = ClientFactory()
        already = ClientFactory(status="blocked")

        with caplog.at_level(logging.INFO, logger="sam.audit"):
            run_action(staff_browser, CLIENTS, "block_accounts", changed.pk, already.pk)

        records = [
            r
            for r in caplog.records
            if r.name == "sam.audit" and r.getMessage() == "admin.account.status"
        ]
        assert [(r.target_id, r.to_status) for r in records] == [
            (str(changed.pk), "blocked")
        ]
        from django.contrib.admin.models import LogEntry

        assert (
            LogEntry.objects.filter(
                object_id=str(changed.pk), change_message__contains="blocked"
            ).count()
            == 1
        )


# ------------------------------------------------------------ anonimização


@pytest.fixture
def client_with_history(media_root):
    from apps.accounts.principal import Principal
    from apps.accounts.services import update_account_profile
    from apps.core.images import process_image

    client = ClientFactory(
        name="Ana Maria Souza", email="ana@exemplo.com", phone_number="86999990000"
    )
    update_account_profile(
        Principal(client, "client"), {"photo_profile": process_image(jpeg_upload())}
    )
    client.refresh_from_db()
    workshop = make_ready_workshop()
    budget, *_ = deliver_attendance(AttendanceFactory(client=client, workshop=workshop))
    make_review(budget, comment="Muito bom")
    FavoriteFactory(client=client, workshop=workshop)
    NotificationFactory(client=client, title="Orçamento recebido")
    return client, workshop


class TestAnonymize:
    def test_first_step_only_asks_for_confirmation(
        self, staff_browser, client_with_history
    ):
        client, _ = client_with_history

        response = run_action(staff_browser, CLIENTS, "anonymize_accounts", client.pk)

        assert response.status_code == 200
        page = response.content.decode()
        assert "irreversível" in page and 'name="confirm" value="yes"' in page
        client.refresh_from_db()
        assert client.name == "Ana Maria Souza"

    def test_client_personal_data_is_gone_and_history_remains(
        self,
        staff_browser,
        api_client,
        account_session,
        client_with_history,
        django_capture_on_commit_callbacks,
    ):
        client, workshop = client_with_history
        photo = client.photo_profile
        old_hash = client.password_hash
        session = account_session(client, "client")
        assert default_storage.exists(photo)

        with django_capture_on_commit_callbacks(execute=True):
            response = run_action(
                staff_browser, CLIENTS, "anonymize_accounts", client.pk, confirm="yes"
            )

        assert response.status_code == 302
        client.refresh_from_db()
        assert client.name == "Anônimo"
        assert client.email == f"anonimo-client-{client.pk}@anonimizado.invalid"
        assert (client.phone_number, client.photo_profile, client.status) == (
            None,
            None,
            "inactive",
        )
        assert client.password_hash != old_hash and client.password_hash.startswith("!")
        assert not default_storage.exists(photo)
        # o histórico continua: atendimento, orçamento, registro de manutenção e avaliação
        assert Attendance.objects.filter(client=client).count() == 1
        assert Review.objects.filter(budget__attendance__client=client).count() == 1
        public = api_client.get(f"/api/workshops/{workshop.pk}/reviews/").json()[
            "results"
        ]
        assert [r["client_name"] for r in public] == ["Anônimo"]
        # nada pessoal recuperável pelos caminhos de login e sessão
        assert not Favorite.objects.filter(client=client).exists()
        assert not Notification.objects.filter(client=client).exists()
        assert session.get("/api/auth/me/").status_code == 401
        assert login(api_client, "client", "ana@exemplo.com").status_code == 401
        assert login(api_client, "client", client.email, password="").status_code in (
            400,
            401,
        )
        assert "ana@exemplo.com" not in str(
            Client.objects.filter(pk=client.pk).values().first()
        )
        assert "Ana" not in str(Client.objects.filter(pk=client.pk).values().first())
        # o e-mail fica livre para um novo cadastro
        register = api_client.post(
            "/api/auth/register/",
            {
                "role": "client",
                "name": "Ana Nova",
                "email": "ana@exemplo.com",
                "password": "OutraSenha123",
            },
            format="json",
        )
        assert register.status_code == 201

    def test_workshop_keeps_company_data_and_loses_personal_data(
        self, staff_browser, api_client, django_capture_on_commit_callbacks
    ):
        workshop = make_ready_workshop()
        Workshop.objects.filter(pk=workshop.pk).update(
            name_responsible="Carlos Pereira", phone_number="86988887777"
        )
        PagWorkshop.objects.filter(workshop=workshop).update(
            photo_banner="banners/b.jpg"
        )
        default_storage.save("banners/b.jpg", jpeg_upload())
        attendance = AttendanceFactory(workshop=workshop)

        with django_capture_on_commit_callbacks(execute=True):
            run_action(
                staff_browser,
                WORKSHOPS,
                "anonymize_accounts",
                workshop.pk,
                confirm="yes",
            )

        workshop.refresh_from_db()
        assert (workshop.name_responsible, workshop.phone_number, workshop.status) == (
            "Anônimo",
            None,
            "inactive",
        )
        assert workshop.email == f"anonimo-workshop-{workshop.pk}@anonimizado.invalid"
        assert workshop.name_fantasy.startswith("Oficina") and len(workshop.cnpj) == 14
        page = PagWorkshop.objects.get(workshop=workshop)
        assert (page.photo_profile, page.photo_banner) == ("default-profile.png", None)
        assert not default_storage.exists("banners/b.jpg")
        assert Attendance.objects.filter(pk=attendance.pk, workshop=workshop).exists()
        assert api_client.get(f"/api/workshops/{workshop.pk}/").status_code == 404

    def test_anonymized_account_cannot_be_reactivated(self, staff_browser, api_client):
        client = ClientFactory()
        run_action(
            staff_browser, CLIENTS, "anonymize_accounts", client.pk, confirm="yes"
        )

        run_action(staff_browser, CLIENTS, "activate_accounts", client.pk)
        form = staff_browser.post(
            f"{CLIENTS}{client.pk}/change/",
            {"name": "Anônimo", "phone_number": "", "status": "active"},
        )

        assert (
            form.status_code == 200
            and "não pode ser reativada" in form.content.decode()
        )
        assert Client.objects.get(pk=client.pk).status == "inactive"

    def test_anonymization_is_audited(self, staff_browser, caplog):
        client = ClientFactory()

        with caplog.at_level(logging.INFO, logger="sam.audit"):
            run_action(
                staff_browser, CLIENTS, "anonymize_accounts", client.pk, confirm="yes"
            )

        [record] = [
            r
            for r in caplog.records
            if r.name == "sam.audit" and r.getMessage() == "admin.account.anonymize"
        ]
        assert (record.target_type, record.target_id) == ("client", str(client.pk))
        assert "@exemplo.com" not in str(record.__dict__)
