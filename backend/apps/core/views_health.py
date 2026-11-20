from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import heartbeat
from .checks import MIN_POSTGRES_VERSION

HealthStatus = inline_serializer("HealthStatus", {"status": serializers.CharField()})


@extend_schema(responses=HealthStatus, summary="Liveness: o processo está vivo")
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_live(request):
    return Response({"status": "ok"})


@extend_schema(
    responses={200: HealthStatus, 503: HealthStatus},
    summary="Readiness: banco acessível e schema presente",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("SHOW server_version_num")
            version = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT to_regclass('public.client') IS NOT NULL "
                "AND to_regprocedure('public.run_expiration_jobs()') IS NOT NULL"
            )
            schema_ready = cursor.fetchone()[0]
    except DatabaseError:
        return Response(
            {"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if version < MIN_POSTGRES_VERSION or not schema_ready:
        return Response(
            {"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return Response({"status": "ok"})


@extend_schema(
    responses={200: HealthStatus, 503: HealthStatus},
    summary="Rotina de expiração: última execução bem-sucedida recente",
    description=(
        "200 `ok` se `run_expiration_jobs` terminou com sucesso há no máximo "
        "`SAM_EXPIRATION_MAX_AGE` segundos (padrão 15 min); 503 `stale` se parou ou se a "
        "última execução falhou; 503 `unavailable` sem banco. Para monitor externo "
        "(BE-092): sem orçamentos e promoções expirando, o sistema mostra dados vencidos."
    ),
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_jobs(request):
    try:
        job = heartbeat.job_status(heartbeat.EXPIRATION)
    except DatabaseError:
        return Response(
            {"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    if not job.ok:
        return Response({"status": "stale"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"status": "ok"})
