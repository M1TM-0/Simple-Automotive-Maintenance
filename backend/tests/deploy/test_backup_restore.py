"""BE-090 — Backup e restauração (deploy/backup/), ensaio automatizado.

Critérios da tarefa:
* "Dado o backup mais recente, quando restaurado em ambiente limpo, então a API sobe e
  os dados conferem (contagens por tabela e imagens)" → `test_backup_restores_*`:
  backup do banco de teste (com escrita concorrente durante o dump) + mídia, restauração
  num banco NOVO e num diretório vazio, conferência pelo próprio `sam-restore`, depois
  `migrate --check` e `/api/health/ready/` com a API apontando para o banco restaurado.
* "Dado a falha do backup, então há alerta" → `test_failed_backup_*`: webhook recebe o
  alerta e o batimento `backup` fica com a falha (o monitor também alerta, BE-092).

Precisa de bash, psql/pg_dump/pg_restore DA MESMA VERSÃO do servidor, gpg, jq, tar e
permissão de CREATE DATABASE. Sem isso o teste é pulado — no CI
(SAM_REQUIRE_DEPLOY_TOOLS=1) vira falha, para nunca passar em silêncio.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from apps.core import heartbeat
from apps.core.tests.world import build_world
from django.db import connection

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "deploy" / "backup"
BACKEND = REPO / "backend"
TOOLS = (
    "bash",
    "psql",
    "pg_dump",
    "pg_restore",
    "gpg",
    "jq",
    "tar",
    "sha256sum",
    "curl",
)

pytestmark = [pytest.mark.deploy, pytest.mark.django_db(transaction=True)]


def _unavailable(reason):
    if os.environ.get("SAM_REQUIRE_DEPLOY_TOOLS") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def libpq(db):
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if missing:
        _unavailable(f"ferramentas ausentes: {missing}")
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        server = int(cursor.fetchone()[0]) // 10000
    client = subprocess.run(
        ["pg_dump", "--version"], capture_output=True, text=True
    ).stdout
    if str(server) not in client.split()[-1].split(".")[0]:
        _unavailable(f"pg_dump ({client.strip()}) × servidor PostgreSQL {server}")
    settings = connection.settings_dict
    return {
        "PGHOST": settings["HOST"] or "localhost",
        "PGPORT": str(settings["PORT"] or 5432),
        "PGUSER": settings["USER"] or "",
        "PGPASSWORD": settings["PASSWORD"] or "",
        "PGDATABASE": settings["NAME"],
    }


@pytest.fixture
def scratch_db(libpq):
    """Banco novo e vazio (ambiente limpo da restauração); apagado no fim."""
    name = f"sam_restore_{uuid.uuid4().hex[:10]}"
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE "{name}"')  # sql-safe: nome gerado acima
    yield name
    with connection.cursor() as cursor:
        cursor.execute(
            f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'
        )  # sql-safe: idem


@pytest.fixture
def paths(tmp_path):
    media = tmp_path / "media"
    for name, size in (
        ("vehicles/a1.jpg", 2048),
        ("vehicles/b2.png", 1024),
        ("profiles/c3.webp", 512),
    ):
        (media / name).parent.mkdir(parents=True, exist_ok=True)
        (media / name).write_bytes(os.urandom(size))
    backups = tmp_path / "backups"
    backups.mkdir()
    secret = tmp_path / "passphrase"
    secret.write_text(uuid.uuid4().hex)
    return {"media": media, "backups": backups, "passphrase": secret, "tmp": tmp_path}


def run(script, *args, env=None, check=True):
    result = subprocess.run(
        [str(SCRIPTS / script), *args],
        env={**os.environ, "SAM_ENVIRONMENT": "teste", **(env or {})},
        capture_output=True,
        text=True,
        timeout=180,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def backup_env(libpq, paths, **extra):
    return {
        **libpq,
        "BACKUP_DIR": str(paths["backups"]),
        "MEDIA_DIR": str(paths["media"]),
        "BACKUP_PASSPHRASE_FILE": str(paths["passphrase"]),
        **extra,
    }


def restore_env(libpq, paths, database, **extra):
    return {**backup_env(libpq, paths, **extra), "PGDATABASE": database}


def count_clients():
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM client")
        return cursor.fetchone()[0]


def api_against(libpq, database, code):
    """Roda `code` num processo Django apontado para o banco restaurado (a API "sobe")."""
    url = f"postgres://{libpq['PGUSER']}:{libpq['PGPASSWORD']}@{libpq['PGHOST']}:{libpq['PGPORT']}/{database}"
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.test",
        "TEST_DATABASE_URL": url,
    }
    env.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


CHECK_RESTORED_API = """
import django, json
django.setup()
from django.core.management import call_command
from django.test import Client
call_command("migrate", "--check", verbosity=0)   # nenhuma migration pendente
from apps.accounts.models import Client as Customer
response = Client().get("/api/health/ready/")
print(json.dumps({"ready": response.status_code, "clients": Customer.objects.count()}))
"""


class _Writer(threading.Thread):
    """Grava notificações sem parar enquanto o backup roda (prova do snapshot único)."""

    def __init__(self, libpq, client_id):
        super().__init__(daemon=True)
        self.libpq, self.client_id, self.stop, self.rows = (
            libpq,
            client_id,
            threading.Event(),
            0,
        )

    def run(self):
        import psycopg

        dsn = " ".join(
            f"{k[2:].lower()}={v}"
            for k, v in self.libpq.items()
            if v and k != "PGDATABASE"
        )
        with psycopg.connect(
            f"{dsn} dbname={self.libpq['PGDATABASE']}", autocommit=True
        ) as conn:
            while not self.stop.is_set():
                conn.execute(
                    "INSERT INTO notification (id_client, title, message, url) VALUES (%s, 'x', 'durante o backup', NULL)",
                    [self.client_id],
                )
                self.rows += 1
                time.sleep(0.002)


def test_backup_restores_in_a_clean_environment_and_the_api_comes_up(
    libpq, scratch_db, paths
):
    world = build_world()
    writer = _Writer(libpq, world.a.client.pk)
    writer.start()
    try:
        archive = Path(run("sam-backup", env=backup_env(libpq, paths)).stdout.strip())
    finally:
        writer.stop.set()
        writer.join()
    assert writer.rows > 0  # houve escrita concorrente durante o dump

    assert archive.name.startswith("sam-") and archive.suffix == ".gpg"
    assert Path(f"{archive}.sha256").exists()
    status = heartbeat.job_status(heartbeat.BACKUP)
    assert status.ok

    restored_media = paths["tmp"] / "restored-media"
    result = run(
        "sam-restore",
        "latest",
        "--media-dir",
        str(restored_media),
        env=restore_env(libpq, paths, scratch_db),
    )
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["media_files"] == 3
    assert report["tables"] >= 25 and report["rows"] > 0
    # BE-094: além das contagens, o md5 do conteúdo de cada tabela confere.
    assert report["content_checked_tables"] == report["tables"]

    # Imagens idênticas, byte a byte.
    for original in paths["media"].rglob("*.*"):
        copy = restored_media / original.relative_to(paths["media"])
        assert copy.read_bytes() == original.read_bytes()

    # A API sobe sobre o banco restaurado.
    out = json.loads(
        api_against(libpq, scratch_db, CHECK_RESTORED_API).strip().splitlines()[-1]
    )
    assert out == {"ready": 200, "clients": count_clients()}


def test_backup_with_public_key_needs_the_private_key_to_restore(
    libpq, scratch_db, paths
):
    gnupg = paths["tmp"] / "gnupg"
    gnupg.mkdir(mode=0o700)
    gpg = ["gpg", "--homedir", str(gnupg), "--batch"]
    subprocess.run(
        [
            *gpg,
            "--passphrase",
            "",
            "--quick-gen-key",
            "SAM Backup <backup@exemplo.invalid>",
            "future-default",
            "default",
            "never",
        ],
        check=True,
        capture_output=True,
    )
    public, private = paths["tmp"] / "backup.pub.asc", paths["tmp"] / "backup.key.asc"
    public.write_bytes(
        subprocess.run(
            [*gpg, "--armor", "--export"], check=True, capture_output=True
        ).stdout
    )
    private.write_bytes(
        subprocess.run(
            [*gpg, "--armor", "--export-secret-keys"], check=True, capture_output=True
        ).stdout
    )

    env = backup_env(libpq, paths, BACKUP_GPG_RECIPIENT_FILE=str(public))
    env.pop("BACKUP_PASSPHRASE_FILE")
    run("sam-backup", env=env)

    no_key = restore_env(libpq, paths, scratch_db)
    no_key.pop("BACKUP_PASSPHRASE_FILE")
    failed = run(
        "sam-restore",
        "latest",
        "--media-dir",
        str(paths["tmp"] / "m1"),
        env=no_key,
        check=False,
    )
    assert failed.returncode != 0 and "decifrar" in failed.stderr

    ok = run(
        "sam-restore",
        "latest",
        "--media-dir",
        str(paths["tmp"] / "m2"),
        env={**no_key, "BACKUP_GPG_PRIVATE_KEY_FILE": str(private)},
    )
    assert json.loads(ok.stdout.strip().splitlines()[-1])["media_files"] == 3


def test_restore_refuses_a_database_that_is_not_empty(libpq, paths):
    run("sam-backup", env=backup_env(libpq, paths))

    result = run(
        "sam-restore",
        "latest",
        "--media-dir",
        str(paths["tmp"] / "m"),
        env=restore_env(libpq, paths, libpq["PGDATABASE"]),
        check=False,
    )

    assert result.returncode != 0 and "não está vazio" in result.stderr


def test_restore_refuses_a_corrupted_archive_and_a_wrong_passphrase(
    libpq, scratch_db, paths
):
    archive = Path(run("sam-backup", env=backup_env(libpq, paths)).stdout.strip())
    env = restore_env(libpq, paths, scratch_db)

    wrong = paths["tmp"] / "wrong"
    wrong.write_text("outra-frase")
    result = run(
        "sam-restore",
        str(archive),
        "--media-dir",
        str(paths["tmp"] / "m1"),
        env={**env, "BACKUP_PASSPHRASE_FILE": str(wrong)},
        check=False,
    )
    assert result.returncode != 0 and "decifrar" in result.stderr

    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0xFF
    archive.write_bytes(bytes(data))
    result = run(
        "sam-restore",
        str(archive),
        "--media-dir",
        str(paths["tmp"] / "m2"),
        env=env,
        check=False,
    )
    assert result.returncode != 0 and "não confere" in result.stderr


@pytest.fixture
def webhook():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            received.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/alerta", received
    server.shutdown()


def test_failed_backup_alerts_and_marks_the_heartbeat(libpq, paths, webhook):
    url, received = webhook
    heartbeat.record_success(heartbeat.BACKUP)
    env = backup_env(
        libpq,
        paths,
        MEDIA_DIR=str(paths["tmp"] / "nao-existe"),
        SAM_ALERT_WEBHOOK_URL=url,
    )

    result = run("sam-backup", env=env, check=False)

    assert result.returncode == 1
    assert len(received) == 1 and "Backup falhou" in received[0]["text"]
    assert (
        received[0]["text"] == received[0]["content"]
    )  # Slack lê `text`, Discord `content`
    assert heartbeat.job_status(heartbeat.BACKUP).failing
    assert not list(paths["backups"].glob("sam-*"))


def test_failed_backup_with_database_down_still_alerts(libpq, paths, webhook):
    url, received = webhook
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = str(sock.getsockname()[1])
    env = backup_env(
        libpq, paths, PGHOST="127.0.0.1", PGPORT=closed_port, SAM_ALERT_WEBHOOK_URL=url
    )

    result = run("sam-backup", env=env, check=False)

    assert result.returncode == 1
    assert received and "Banco inacessível" in received[0]["text"]


def test_backup_without_encryption_is_refused(libpq, paths, webhook):
    url, received = webhook
    env = backup_env(libpq, paths, SAM_ALERT_WEBHOOK_URL=url)
    env.pop("BACKUP_PASSPHRASE_FILE")

    result = run("sam-backup", env=env, check=False)

    assert result.returncode == 1 and "sem cifra" in result.stderr
    assert received


def test_local_retention_keeps_recent_and_a_minimum(libpq, paths):
    old = time.time() - 40 * 86400
    names = [f"sam-2026010{d}T030000Z.tar.gpg" for d in range(1, 6)]
    for name in names:
        for path in (paths["backups"] / name, paths["backups"] / f"{name}.sha256"):
            path.write_text("antigo")
            os.utime(path, (old, old))

    archive = Path(
        run(
            "sam-backup",
            env=backup_env(libpq, paths, BACKUP_KEEP_DAYS="14", BACKUP_KEEP_MIN="3"),
        ).stdout.strip()
    )

    left = sorted(p.name for p in paths["backups"].glob("sam-*.tar.gpg"))
    # O novo + os 2 antigos mais recentes (mínimo de 3); os outros, velhos, saem.
    assert left == sorted([archive.name, names[4], names[3]])
    assert not (paths["backups"] / f"{names[0]}.sha256").exists()


def test_scheduler_runs_once_a_day_and_survives_restarts(tmp_path):
    """sam-backup-loop com um sam-backup falso: decide "é hora?" pelo estado salvo."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("lib.sh", "sam-backup-loop"):
        shutil.copy(SCRIPTS / name, bin_dir / name)
    calls = tmp_path / "calls"
    fake = bin_dir / "sam-backup"
    fake.write_text(f"#!/usr/bin/env bash\necho x >> {calls}\n")
    fake.chmod(0o755)
    backups = tmp_path / "backups"
    backups.mkdir()
    env = {
        **os.environ,
        "BACKUP_DIR": str(backups),
        "BACKUP_CHECK_SECONDS": "1",
        "BACKUP_RETRY_SECONDS": "0",
    }

    def run_loop(seconds):
        proc = subprocess.Popen(
            [str(bin_dir / "sam-backup-loop")], env=env, stderr=subprocess.PIPE
        )
        time.sleep(seconds)
        proc.terminate()
        assert proc.wait(10) == 0

    run_loop(2.5)  # nunca houve backup: roda já, e só uma vez
    assert calls.read_text().count("x") == 1
    run_loop(1.5)  # reinício do contêiner: o último sucesso é recente, não roda
    assert calls.read_text().count("x") == 1

    (backups / ".state").write_text(
        f"last_success={int(time.time()) - 27 * 3600}\nlast_attempt=0\n"
    )
    run_loop(1.5)  # último sucesso há 27 h (atrasado): roda já
    assert calls.read_text().count("x") == 2


def test_restore_detects_content_that_differs_from_the_manifest(
    libpq, scratch_db, paths
):
    """BE-094: contagens iguais não bastam — o md5 do conteúdo de cada tabela é conferido."""
    import tarfile

    build_world()
    archive = Path(
        run(
            "sam-backup",
            env=backup_env(
                libpq, paths, BACKUP_ALLOW_UNENCRYPTED="1", BACKUP_PASSPHRASE_FILE=""
            ),
        ).stdout.strip()
    )
    assert archive.suffix == ".tar"
    work = paths["tmp"] / "repack"
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    manifest = json.loads((work / "manifest.json").read_text())
    assert set(manifest["checksums"]) == set(manifest["tables"])
    assert all(len(h) == 32 for h in manifest["checksums"].values())
    # Simula um dump cujo conteúdo não é o do manifesto (mesmas contagens).
    manifest["checksums"]["client"] = "0" * 32
    (work / "manifest.json").write_text(json.dumps(manifest))
    tampered = paths["backups"] / "sam-29990101T000000Z.tar"
    with tarfile.open(tampered, "w") as tar:
        for name in ("manifest.json", "db.dump", "media.tar", "media.sha256"):
            tar.add(work / name, arcname=name)

    result = run(
        "sam-restore",
        str(tampered),
        "--media-dir",
        str(paths["tmp"] / "restored-media"),
        env=restore_env(libpq, paths, scratch_db),
        check=False,
    )

    assert result.returncode == 1
    assert "Conteúdo divergente" in result.stderr and "client" in result.stderr


def test_scheduler_keeps_the_daily_hour_and_catches_up(tmp_path):
    """RPO 24 h (BE-094): roda se não houve sucesso desde a última ocorrência de
    BACKUP_HOUR — às 03h todo dia, e logo que o contêiner volta se estava parado.

    Regressão: a regra antiga (">20 h e hora certa", senão ">26 h") com a primeira
    execução depois das 07h pulava as 03h e passava a rodar a cada 26 h."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("lib.sh", "sam-backup-loop"):
        shutil.copy(SCRIPTS / name, bin_dir / name)
    calls = tmp_path / "calls"
    fake = bin_dir / "sam-backup"
    fake.write_text(f"#!/usr/bin/env bash\necho x >> {calls}\n")
    fake.chmod(0o755)
    backups = tmp_path / "backups"
    backups.mkdir()
    now_hour = int(time.strftime("%H"))

    def runs(hour, last_success_hours_ago):
        before = calls.read_text().count("x") if calls.exists() else 0
        last = int(time.time()) - int(last_success_hours_ago * 3600)
        (backups / ".state").write_text(f"last_success={last}\nlast_attempt=0\n")
        env = {
            **os.environ,
            "BACKUP_DIR": str(backups),
            "BACKUP_CHECK_SECONDS": "1",
            "BACKUP_RETRY_SECONDS": "0",
            "BACKUP_HOUR": f"{hour:02d}",
        }
        proc = subprocess.Popen(
            [str(bin_dir / "sam-backup-loop")], env=env, stderr=subprocess.PIPE
        )
        time.sleep(1.5)
        proc.terminate()
        assert proc.wait(10) == 0
        return calls.read_text().count("x") - before if calls.exists() else 0

    # A hora agendada acabou de passar e o último backup é de 19 h atrás (antes dela):
    # roda. (A regra antiga esperava 20 h e, perdida a janela, 26 h.)
    assert runs(now_hour, 19) == 1
    # Já houve backup depois da última ocorrência da hora agendada: não roda.
    assert runs((now_hour + 1) % 24, 21) == 0
    # Contêiner parado na hora agendada (último sucesso há 25 h): recupera já.
    assert runs((now_hour - 2) % 24, 25) == 1
