from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_password_reset_email(*, to_email: str, token: str, role: str):
    base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5500").rstrip("/")
    link = f"{base}/forgot-password.html?token={token}"
    subject = "Redefinição de senha - SAM"
    context = {"link": link, "token": token, "role": role}
    try:
        body = render_to_string("accounts/password_reset_email.txt", context)
    except Exception:
        body = f"Use o link para redefinir sua senha: {link}"
    try:
        html_body = render_to_string("accounts/password_reset_email.html", context)
    except Exception:
        html_body = None
    send_mail(
        subject,
        body,
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@sam.local",
        [to_email],
        html_message=html_body,
    )
