"""HEALTHCHECK dos contêineres de produção (BE-088, BE-091). Sem Django: rápido e leve.

Modos:

* ``healthcheck.py [caminho]`` — GET em ``http://127.0.0.1:8000<caminho>`` (padrão
  ``/api/health/``, liveness). O Django recusa ``Host`` fora do ``ALLOWED_HOSTS``,
  então a requisição usa o primeiro host da lista. ``/api/health/`` fica fora do
  redirecionamento HTTPS (``SECURE_REDIRECT_EXEMPT``).
* ``healthcheck.py --file ARQUIVO --max-age SEGUNDOS`` — o arquivo foi tocado há no
  máximo SEGUNDOS (batimento da rotina ``run_expiration_jobs --heartbeat-file``).

Sai com 0 (saudável) ou 1.
"""

import argparse
import http.client
import os
import sys
import time


def _host():
    hosts = [
        h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
    ]
    # ".exemplo.com" (subdomínios) também aceita "exemplo.com".
    return hosts[0].lstrip(".") if hosts and hosts[0] != "*" else "localhost"


def check_http(path, port, timeout):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(
            "GET", path, headers={"Host": _host(), "Accept": "application/json"}
        )
        response = conn.getresponse()
        response.read()
    except OSError as exc:
        print(f"unhealthy: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if response.status != 200:
        print(f"unhealthy: HTTP {response.status} em {path}", file=sys.stderr)
        return 1
    return 0


def check_file(path, max_age):
    try:
        age = time.time() - os.stat(path).st_mtime
    except FileNotFoundError:
        print(f"unhealthy: {path} ainda não existe", file=sys.stderr)
        return 1
    if age > max_age:
        print(
            f"unhealthy: último batimento há {age:.0f} s (máximo {max_age} s)",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", default="/api/health/")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SAM_HEALTH_PORT", "8000"))
    )
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--file")
    parser.add_argument("--max-age", type=int, default=300)
    args = parser.parse_args(argv)

    if args.file:
        return check_file(args.file, args.max_age)
    return check_http(args.path, args.port, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
