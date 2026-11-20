# Imagem do serviço `backup` (BE-090). Mesma versão principal do PostgreSQL do serviço
# `db`: pg_dump/pg_restore de outra versão geram dumps que o servidor não restaura.
#   docker build -t sam-backup deploy/backup
ARG POSTGRES_IMAGE=postgres:16-bookworm
FROM ${POSTGRES_IMAGE}

# gnupg (cifra), jq (manifesto e logs), curl (alerta por webhook), rclone (cópia fora
# do servidor: S3, B2, SFTP, Google Drive…).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gnupg jq curl ca-certificates rclone \
    && rm -rf /var/lib/apt/lists/*

COPY lib.sh sam-backup sam-restore sam-backup-loop /opt/sam-backup/
RUN chmod 0755 /opt/sam-backup/sam-* \
    && ln -s /opt/sam-backup/sam-backup /usr/local/bin/sam-backup \
    && ln -s /opt/sam-backup/sam-restore /usr/local/bin/sam-restore \
    && install -d -o postgres -g postgres -m 0750 /backups

ENV BACKUP_DIR=/backups \
    MEDIA_DIR=/media

# Usuário sem privilégios (o da imagem do PostgreSQL). A restauração da mídia num
# volume do usuário da API roda como root (`--user 0`, ver RUNBOOK.md).
USER postgres
WORKDIR /backups

# Sem o entrypoint do PostgreSQL (este contêiner não roda um servidor).
ENTRYPOINT []
CMD ["/opt/sam-backup/sam-backup-loop"]
