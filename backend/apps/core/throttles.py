"""Limites de taxa e proteção contra força bruta (BE-033).

Os contadores ficam no cache `default`. Em produção ele precisa ser compartilhado
entre processos (DatabaseCache por padrão, ver `config/settings/prod.py`); com
`LocMemCache` cada worker do Gunicorn teria o próprio contador.
"""

import time

from django.conf import settings
from django.core.cache import cache as default_cache
from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle


def client_ip(request) -> str:
    """IP do cliente com a mesma regra do DRF (respeita NUM_PROXIES)."""
    return BaseThrottle().get_ident(request)


def _body_value(request, key):
    data = getattr(request, "data", None) or {}
    try:
        return str(data.get(key, "")).strip().lower()
    except AttributeError:
        return ""


def _user_ident(request):
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"{getattr(user, 'role', 'user')}:{user.pk}"
    return None


class LoginRateThrottle(SimpleRateThrottle):
    """`login`: por IP + perfil + e-mail (o 6º login em 1 min recebe 429)."""

    scope = "login"

    def get_cache_key(self, request, view):
        ident = f"{self.get_ident(request)}:{_body_value(request, 'role')}:{_body_value(request, 'email')}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class RegisterRateThrottle(SimpleRateThrottle):
    """`register`: por IP."""

    scope = "register"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class PasswordResetRateThrottle(SimpleRateThrottle):
    """`reset`: por IP + e-mail (a confirmação, sem e-mail, fica só por IP)."""

    scope = "reset"

    def get_cache_key(self, request, view):
        ident = f"{self.get_ident(request)}:{_body_value(request, 'email')}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class MessageRateThrottle(SimpleRateThrottle):
    """`message`: envio de mensagens do chat, por usuário. Leituras não contam."""

    scope = "message"

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        ident = _user_ident(request) or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PollingRateThrottle(SimpleRateThrottle):
    """`polling`: leituras periódicas (mensagens a cada 5 s, sino a cada 60 s).

    Limite folgado por usuário: só barra abuso, nunca o polling legítimo.
    """

    scope = "polling"

    def allow_request(self, request, view):
        if request.method not in SAFE_METHODS:
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        ident = _user_ident(request) or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ExternalMapRateThrottle(SimpleRateThrottle):
    """`external_map`: estabelecimentos do OpenStreetMap no mapa (BE-094), por IP.

    Cada movimento do mapa pede a região visível; o limite só barra abuso — a proteção
    da Overpass pública é o cache e o orçamento global de `apps/workshops/overpass.py`.
    """

    scope = "external_map"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class ProgressiveLockout:
    """Bloqueio temporário progressivo após falhas repetidas.

    Ao atingir `threshold` falhas (contadas numa janela deslizante de
    `window_seconds`), o identificador fica bloqueado por `base_seconds`; cada
    nova falha depois disso dobra o bloqueio, até `max_seconds`. Um sucesso zera.
    """

    def __init__(
        self,
        scope,
        *,
        threshold,
        base_seconds,
        max_seconds,
        window_seconds,
        cache=None,
        timer=None,
    ):
        self.scope = scope
        self.threshold = threshold
        self.base_seconds = base_seconds
        self.max_seconds = max_seconds
        self.window_seconds = window_seconds
        self.cache = cache or default_cache
        self.timer = timer

    def _now(self):
        # Lido a cada chamada (não no import) para os testes poderem controlar o relógio.
        return self.timer() if self.timer is not None else time.time()

    def _keys(self, ident):
        return (
            f"sam:lockout:{self.scope}:fail:{ident}",
            f"sam:lockout:{self.scope}:until:{ident}",
        )

    def retry_after(self, ident) -> int:
        """Segundos restantes de bloqueio (0 = liberado)."""
        _, lock_key = self._keys(ident)
        until = self.cache.get(lock_key)
        if not until:
            return 0
        remaining = until - self._now()
        return max(int(remaining + 0.999), 0)

    def register_failure(self, ident) -> int:
        """Conta uma falha; devolve a duração do bloqueio aplicado (0 se nenhum)."""
        fail_key, lock_key = self._keys(ident)
        failures = (self.cache.get(fail_key) or 0) + 1
        self.cache.set(fail_key, failures, self.window_seconds)
        if failures < self.threshold:
            return 0
        duration = min(
            self.base_seconds * 2 ** (failures - self.threshold), self.max_seconds
        )
        self.cache.set(lock_key, self._now() + duration, duration)
        return duration

    def reset(self, ident) -> None:
        self.cache.delete_many(list(self._keys(ident)))


def login_lockouts():
    """Bloqueios do login: por IP+conta (limiar baixo) e por conta (contra ataque distribuído)."""
    conf = settings.SAM_LOGIN_LOCKOUT
    common = {
        "base_seconds": conf["BASE_SECONDS"],
        "max_seconds": conf["MAX_SECONDS"],
        "window_seconds": conf["WINDOW_SECONDS"],
    }
    return (
        ProgressiveLockout("login-ip", threshold=conf["THRESHOLD"], **common),
        ProgressiveLockout(
            "login-account", threshold=conf["ACCOUNT_THRESHOLD"], **common
        ),
    )
