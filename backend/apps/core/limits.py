"""Limites de entrada impostos pelo servidor (BE-086, DP-19).

Texto: o limite é o `maxlength` da tela que envia o campo (DP-19). As colunas abaixo
são `TEXT` no banco, que não limita nada — sem estes números o servidor aceitaria
megabytes num comentário. Colunas `VARCHAR(n)` já são limitadas pelo banco e os
serializers repetem o `n` (255 na maioria) só para responder 400 em vez de 409.

`tests/security/test_input_limits.py` prova cada limite (no limite → aceito; um a mais
→ 400) e confere que a tela usa o mesmo `maxlength`.

Corpo da requisição: `RequestSizeLimitMiddleware` (`apps/core/middleware.py`) responde
413 pelo `Content-Length`, antes de qualquer leitura do corpo.
"""

from rest_framework.exceptions import ValidationError

# ------------------------------------------------------------------ texto
MESSAGE = 2000  # chat (T07, chat.js)
OBSERVATIONS = 1000  # pedido do cliente e notas técnicas do atendimento (T14/T19)
BUDGET_OBSERVATIONS = 1000  # observações do orçamento (T20)
REVIEW_COMMENT = 500  # avaliação (T14, attendance-parts.js)
REVIEW_RESPONSE = 1000  # resposta pública da oficina (T26, w-reviews.js)
DENUNCIATION_DESCRIPTION = 500  # denúncia (C02, components-parts.js)
VEHICLE_INFORMATION = 600  # informações do veículo (T11, vehicle-new.js)
HISTORY_OBSERVATIONS = 200  # registro manual do histórico (T12, vehicle.js)
DESCRIPTION = 1000  # página da oficina, produto, promoção, serviço personalizado
ADDRESS = 500  # endereço do ponto no mapa (T17)
MODERATION_DECISION = 2000  # decisão do moderador (admin)
REJECTION_MOTIVATION = 1000  # motivo da rejeição de serviço personalizado (admin)

# ------------------------------------------------------------ credenciais
EMAIL = 254  # RFC 5321
PASSWORD = 128  # o hash (Argon2) roda sobre a senha inteira: sem teto vira custo de CPU
TOKEN = 1024  # token de redefinição de senha

# ---------------------------------------------------------------- busca
SEARCH = 100  # `?q=` do mapa, home, catálogo e pontos de interesse (maxlength 100)

NUL_MESSAGE = "Caracteres nulos não são permitidos."


def clean_query_text(value, field="q", max_length=SEARCH):
    """Texto de busca vindo da query string: sem NUL e no máximo `max_length` caracteres.

    O NUL chegaria ao PostgreSQL (que recusa `\\x00` em texto) e viraria 500.
    """
    if value is None:
        return ""
    text = str(value)
    if "\x00" in text:
        raise ValidationError({field: [NUL_MESSAGE]})
    if len(text) > max_length:
        raise ValidationError({field: [f"Use no máximo {max_length} caracteres."]})
    return text
