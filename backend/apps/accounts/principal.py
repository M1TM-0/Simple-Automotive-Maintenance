from apps.accounts.models import AccountStatus


class Principal:
    """Identidade autenticada de domínio exposta em `request.user` (BE-025).

    `role` é `client` ou `workshop`; `id` é a PK da conta; `account`/`entity` é a
    instância de Client/Workshop carregada pela autenticação.
    """

    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False

    def __init__(self, account, role):
        self.account = account
        self.entity = account
        self.role = role
        self.pk = account.pk
        self.id = account.pk
        self.is_active = account.status == AccountStatus.ACTIVE

    def __repr__(self):
        return f"<Principal {self.role}:{self.id}>"

    @property
    def email(self):
        return self.account.email

    @property
    def name(self):
        if self.role == "client":
            return self.account.name
        return self.account.name_fantasy
