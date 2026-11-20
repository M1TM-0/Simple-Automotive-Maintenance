"""App WSGI mínima para provar o encerramento controlado do Gunicorn (BE-088).

`GET /slow?segundos` dorme e responde 200; antes de dormir cria o arquivo de
`SAM_SLOW_APP_MARKER`, para o teste saber que a requisição já está em andamento.
"""

import os
import time
from pathlib import Path


def application(environ, start_response):
    if environ["PATH_INFO"] != "/slow":
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]
    seconds = float(environ.get("QUERY_STRING") or "2")
    Path(os.environ["SAM_SLOW_APP_MARKER"]).touch()
    time.sleep(seconds)
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"terminou"]
