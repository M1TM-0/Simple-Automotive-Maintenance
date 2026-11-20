import contextvars
import json
import logging
import re
from datetime import UTC, datetime

request_id_var = contextvars.ContextVar("request_id", default="-")
log_user_var = contextvars.ContextVar("log_user", default="anonymous")

SENSITIVE_KEYS = (
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "token",
    "sessionid",
    "csrftoken",
    "authorization",
    "cookie",
    "secret",
)
MASK = "***"

_KEYS = "|".join(SENSITIVE_KEYS)
_PATTERNS = (
    re.compile(r"(?P<k>\b(?:Bearer|Basic)\s+)(?P<q>)(?P<v>[A-Za-z0-9._~+/=-]+)", re.I),
    re.compile(
        rf"""(?P<k>["']?(?:{_KEYS})["']?\s*[:=]\s*)(?P<q>["']?)(?P<v>[^\s"',;}}]+)""",
        re.I,
    ),
)

RESERVED_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "request_id",
    "user",
}


def mask_secrets(text):
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: f"{m['k']}{m['q']}{MASK}", text)
    return text


_SENSITIVE_KEY = re.compile("|".join(map(re.escape, SENSITIVE_KEYS)), re.I)


def mask_value(key, value):
    """Mascara um campo `extra` do log: pela chave (password, token...) ou pelo conteúdo do texto."""
    if isinstance(key, str) and _SENSITIVE_KEY.search(key):
        return MASK
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {k: mask_value(k, v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [mask_value(None, v) for v in value]
    return value


def mask_email(email):
    if not email or "@" not in email:
        return MASK
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 2)}@{domain}"


def set_log_user(role, user_id):
    return log_user_var.set(f"{role}:{user_id}")


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.user = log_user_var.get()
        return True


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        record.msg = mask_secrets(record.getMessage())
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user": getattr(record, "user", "anonymous"),
        }

        for key, value in record.__dict__.items():
            if key not in RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = mask_value(key, value)

        if record.exc_info:
            payload["exception"] = mask_secrets(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, default=str)


def log_auth_event(event, *, role, email, ip, success, logger=None, **extra):
    """Registra tentativas de autenticação com e-mail mascarado e nunca a senha."""
    (logger or logging.getLogger("sam.auth")).log(
        logging.INFO if success else logging.WARNING,
        "auth.%s",
        event,
        extra={
            "event": event,
            "role": role,
            "email": mask_email(email),
            "ip": ip,
            "success": success,
            **extra,
        },
    )
