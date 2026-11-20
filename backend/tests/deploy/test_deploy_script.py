"""BE-091 — Ordem e desvios do deploy/deploy.sh, com `docker` e `curl` falsos no PATH.

Critérios da tarefa:
* "Dado uma migration que falha, então a implantação para e a versão anterior continua
  servindo" → o migrate roda num contêiner avulso com a imagem nova; se falha, nenhum
  `up` acontece e o registro de versão não muda.
* "Dado a primeira implantação, então o banco fica com 23 tabelas e o job de expiração
  em execução" → aqui: sem backup, migrate + check_schema (que confere as 23 tabelas do
  init.sql, tests/deploy/test_artifacts.py) e espera do batimento da rotina depois da
  troca. A subida real (Docker de verdade) é o deploy/smoke-test.sh no CI.
"""

import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy" / "deploy.sh"

pytestmark = pytest.mark.deploy

FAKE_DOCKER = r"""#!/usr/bin/env bash
args="$*"
echo "${SAM_VERSION:-}|$args" >> "$FAKE_LOG"
# Como o compose real: o compose.prod.yml exige SAM_VERSION (`${SAM_VERSION:?}`) em
# QUALQUER chamada, até num `exec` no banco (defeito achado na subida real, BE-094).
if [[ "$args" == compose\ -f* && -z "${SAM_VERSION:-}" ]]; then
  echo "error while interpolating services.api.image: required variable SAM_VERSION is missing a value" >&2
  exit 15
fi
case "$args" in
  "compose version") exit 0 ;;
  *" config -q"*) exit 0 ;;
  *" build "*) exit "${FAKE_BUILD:-0}" ;;
  *"up -d --wait db"*) exit 0 ;;
  *"--user 0"*) exit 0 ;;
  *"to_regclass('public.django_migrations')"*) echo "${FAKE_FIRST:-f}"; exit 0 ;;
  *"job_heartbeat"*) echo "${FAKE_JOBS:-t}"; exit 0 ;;
  *"run --rm --no-deps backup"*) exit "${FAKE_BACKUP:-0}" ;;
  *"manage.py migrate"*) exit "${FAKE_MIGRATE:-0}" ;;
  *"manage.py createcachetable"*) exit 0 ;;
  *"manage.py check_schema"*) exit "${FAKE_SCHEMA:-0}" ;;
  *"up -d --remove-orphans"*) echo "$SAM_VERSION" > "$FAKE_RUNNING"; exit 0 ;;
  *" ps"*) exit 0 ;;
esac
echo "docker falso: comando inesperado: $args" >&2
exit 99
"""

FAKE_CURL = r"""#!/usr/bin/env bash
running=$(cat "$FAKE_RUNNING" 2>/dev/null || true)
[[ -n "$running" && "$running" != "${FAKE_UNREADY_VERSION:-}" ]] && exit 0
exit 22
"""


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    certs = tmp_path / "certs"
    certs.mkdir()
    (certs / "fullchain.pem").write_text("cert")
    (certs / "privkey.pem").write_text("key")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "passphrase").write_text("frase")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "SAM_SERVER_NAME=sam.exemplo.com.br\n"
        f"SAM_TLS_DIR={certs}\n"
        f"SAM_BACKUP_SECRETS_DIR={secrets}\n"
        "POSTGRES_DB=sam\nPOSTGRES_USER=sam\nPOSTGRES_PASSWORD=abc123\n"
        "SECRET_KEY=x\n"
        "BACKUP_PASSPHRASE_FILE=/run/secrets/backup/passphrase\n"
    )
    env_file.chmod(0o600)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SAM_ENV_FILE": str(env_file),
        "SAM_STATE_FILE": str(tmp_path / ".deploy-state"),
        "SAM_READY_TIMEOUT": "2",
        "SAM_JOBS_TIMEOUT": "2",
        "FAKE_LOG": str(tmp_path / "docker.log"),
        "FAKE_RUNNING": str(tmp_path / "running"),
        "_tmp": str(tmp_path),
    }


def deploy(env, *args, **fake):
    result = subprocess.run(
        ["bash", str(DEPLOY), *args],
        env={**env, **fake},
        capture_output=True,
        text=True,
        timeout=60,
    )
    log = Path(env["FAKE_LOG"])
    calls = log.read_text().splitlines() if log.exists() else []
    log.unlink(missing_ok=True)
    return result, calls


def state(env):
    path = Path(env["SAM_STATE_FILE"])
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def running(env, version):
    Path(env["FAKE_RUNNING"]).write_text(version)
    Path(env["SAM_STATE_FILE"]).write_text(f"CURRENT={version}\nPREVIOUS=\n")


def index(calls, text):
    return next(i for i, call in enumerate(calls) if text in call)


def test_first_deployment_migrates_without_backup_and_waits_for_the_job(env):
    result, calls = deploy(env, "--version", "v1", FAKE_FIRST="t")

    assert result.returncode == 0, result.stderr
    assert not any("run --rm --no-deps backup" in c for c in calls)
    order = [
        index(calls, s)
        for s in (
            "build",
            "up -d --wait db",
            "manage.py migrate",
            "createcachetable",
            "check_schema",
            "up -d --remove-orphans",
            "job_heartbeat",
        )
    ]
    assert order == sorted(order)
    assert calls[index(calls, "up -d --remove-orphans")].startswith("v1|")
    assert calls[index(calls, "manage.py migrate")].startswith("v1|")  # imagem nova
    assert state(env)["CURRENT"] == "v1"


def test_update_makes_a_backup_before_migrating(env):
    running(env, "v1")

    result, calls = deploy(env, "--version", "v2")

    assert result.returncode == 0, result.stderr
    assert index(calls, "run --rm --no-deps backup") < index(calls, "manage.py migrate")
    assert (state(env)["CURRENT"], state(env)["PREVIOUS"]) == ("v2", "v1")


def test_failing_migration_stops_and_the_previous_version_keeps_serving(env):
    running(env, "v1")

    result, calls = deploy(env, "--version", "v2", FAKE_MIGRATE="1")

    assert result.returncode == 1
    assert "v1 continua no ar" in result.stderr
    assert not any("up -d --remove-orphans" in c for c in calls)  # nada foi trocado
    assert Path(env["FAKE_RUNNING"]).read_text().strip() == "v1"
    assert state(env)["CURRENT"] == "v1"


@pytest.mark.parametrize(
    ("fake", "message"),
    [("FAKE_BACKUP", "Backup falhou"), ("FAKE_SCHEMA", "não confere")],
)
def test_backup_or_schema_failure_also_stops_before_switching(env, fake, message):
    running(env, "v1")

    result, calls = deploy(env, "--version", "v2", **{fake: "1"})

    assert result.returncode == 1 and message in result.stderr
    assert not any("up -d --remove-orphans" in c for c in calls)
    if fake == "FAKE_BACKUP":
        assert not any("manage.py migrate" in c for c in calls)


def test_version_that_does_not_get_ready_is_rolled_back(env):
    running(env, "v1")

    result, calls = deploy(env, "--version", "v2", FAKE_UNREADY_VERSION="v2")

    assert result.returncode == 1
    assert "v1 no ar" in result.stderr
    ups = [c.split("|")[0] for c in calls if "up -d --remove-orphans" in c]
    assert ups == ["v2", "v1"]
    assert Path(env["FAKE_RUNNING"]).read_text().strip() == "v1"
    assert state(env)["CURRENT"] == "v1"


def test_expiration_job_not_running_after_the_switch_is_a_failure(env):
    running(env, "v1")

    result, _ = deploy(env, "--version", "v2", FAKE_JOBS="f")

    assert result.returncode == 1
    assert "rotina de expiração não rodou" in result.stderr


def test_rollback_command_switches_back_to_the_previous_version(env):
    Path(env["FAKE_RUNNING"]).write_text("v2")
    Path(env["SAM_STATE_FILE"]).write_text("CURRENT=v2\nPREVIOUS=v1\n")

    result, calls = deploy(env, "--rollback")

    assert result.returncode == 0, result.stderr
    assert [c.split("|")[0] for c in calls if "up -d --remove-orphans" in c] == ["v1"]
    assert (state(env)["CURRENT"], state(env)["PREVIOUS"]) == ("v1", "v2")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda text: text.replace("SECRET_KEY=x", "SECRET_KEY="), "SECRET_KEY"),
        (
            lambda text: text.replace(
                "POSTGRES_PASSWORD=abc123", "POSTGRES_PASSWORD=a@b/c"
            ),
            "só letras e números",
        ),
        (
            lambda text: text.replace(
                "BACKUP_PASSPHRASE_FILE=/run/secrets/backup/passphrase", ""
            ),
            "backup cifrado",
        ),
    ],
)
def test_preflight_refuses_incomplete_configuration(env, edit, message):
    path = Path(env["SAM_ENV_FILE"])
    path.write_text(edit(path.read_text()))

    result, calls = deploy(env, "--version", "v1")

    assert result.returncode == 1 and message in result.stderr
    assert not any(" build " in c for c in calls)


def test_preflight_requires_the_certificate(env):
    (Path(env["_tmp"]) / "certs" / "privkey.pem").unlink()

    result, calls = deploy(env, "--version", "v1")

    assert result.returncode == 1 and "Certificado ausente" in result.stderr
    assert not calls or not any(" build " in c for c in calls)


def test_invalid_version_is_refused(env):
    result, calls = deploy(env, "--version", "v1;rm -rf /")

    assert result.returncode == 1 and "Versão inválida" in result.stderr
    assert not calls


def test_every_compose_call_has_a_version(env):
    """Regressão (BE-094): `db_psql` chamava o compose sem SAM_VERSION e a primeira
    implantação real parava em "Banco inacessível"."""
    result, calls = deploy(env, "--version", "v1", FAKE_FIRST="t")

    assert result.returncode == 0, result.stderr
    compose_calls = [c for c in calls if "|compose -f" in c]
    assert compose_calls and all(not c.startswith("|") for c in compose_calls)


def test_compose_override_file_is_passed_along(env, tmp_path):
    override = tmp_path / "compose.staging.yml"
    override.write_text("services: {}\n")

    result, calls = deploy(
        env, "--version", "v1", FAKE_FIRST="t", SAM_COMPOSE_OVERRIDE=str(override)
    )

    assert result.returncode == 0, result.stderr
    compose_calls = [c for c in calls if "|compose -f" in c]
    assert all(f"-f compose.prod.yml -f {override}" in c for c in compose_calls)
