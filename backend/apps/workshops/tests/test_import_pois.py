"""BE-071: comando `import_pois` (CSV/GeoJSON, idempotente, relatório de rejeitadas)."""

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from apps.core.tests.factories import PagWorkshopFactory, PointOfInterestFactory
from apps.workshops.models import PointOfInterest
from django.core.management import CommandError, call_command

DATA = Path(__file__).parent / "data"
CSV_FILE = DATA / "pois_exemplo.csv"
GEOJSON_FILE = DATA / "pois_exemplo.geojson"


def run(*args):
    out = StringIO()
    call_command("import_pois", *args, stdout=out)
    return out.getvalue()


def write_csv(
    tmp_path, body, header="external_id,name,type,latitude,longitude,address"
):
    path = tmp_path / "pois.csv"
    path.write_text(f"{header}\n{body}\n", encoding="utf-8")
    return path


@pytest.mark.django_db
class TestImportPois:
    def test_example_csv_imports_valid_rows_and_reports_rejected(self):
        output = run("--file", str(CSV_FILE), "--source", "exemplo")

        assert PointOfInterest.objects.count() == 3
        assert "criados: 3" in output and "rejeitados: 4" in output
        assert "rejeitada (linha 5): Latitude fora do intervalo" in output
        assert "rejeitada (linha 6): Tipo inválido: 'padaria'" in output
        assert "rejeitada (linha 7): external_id ausente" in output
        assert "rejeitada (linha 8): Nome ausente." in output

        third = PointOfInterest.objects.get(
            external_source="exemplo", external_id="ex-3"
        )
        assert (third.latitude, third.longitude) == (
            Decimal("-5.100100"),
            Decimal("-42.790000"),
        )
        assert third.type == "loja_autopecas"
        assert PointOfInterest.objects.get(external_id="ex-2").address is None

    def test_same_file_twice_does_not_change_the_total(self):
        run("--file", str(CSV_FILE), "--source", "exemplo")

        output = run("--file", str(CSV_FILE), "--source", "exemplo")

        assert PointOfInterest.objects.count() == 3
        assert "criados: 0" in output and "sem mudança: 3" in output

    def test_changed_row_updates_the_existing_point(self, tmp_path):
        run(
            "--file",
            str(write_csv(tmp_path, "a1,Nome antigo,borracharia,-5.09,-42.80,")),
            "--source",
            "s",
        )

        output = run(
            "--file",
            str(write_csv(tmp_path, "a1,Nome novo,borracharia,-5.10,-42.80,Rua 2")),
            "--source",
            "s",
        )

        point = PointOfInterest.objects.get()
        assert (point.name, point.latitude, point.address) == (
            "Nome novo",
            Decimal("-5.100000"),
            "Rua 2",
        )
        assert "atualizados: 1" in output

    def test_point_claimed_by_a_workshop_is_preserved(self, tmp_path):
        point = PointOfInterestFactory(
            external_source="s", external_id="a1", name="Escolhido pela oficina"
        )
        PagWorkshopFactory(workshop__point_of_interest=point)

        output = run(
            "--file",
            str(write_csv(tmp_path, "a1,Outro nome,borracharia,-5.2,-42.9,")),
            "--source",
            "s",
        )

        point.refresh_from_db()
        assert point.name == "Escolhido pela oficina"
        assert "vinculados a oficina (preservados): 1" in output

    def test_dry_run_writes_nothing(self):
        output = run("--file", str(CSV_FILE), "--source", "exemplo", "--dry-run")

        assert PointOfInterest.objects.count() == 0
        assert output.startswith("[simulação — nada foi gravado]")
        assert "criados: 3" in output and "rejeitados: 4" in output

    def test_row_with_source_column_and_without_external_id_is_rejected(self, tmp_path):
        path = write_csv(
            tmp_path,
            "osm,,Sem id,oficina,-5.09,-42.80,\nosm,n2,Com id,oficina,-5.09,-42.81,",
            header="external_source,external_id,name,type,latitude,longitude,address",
        )

        output = run("--file", str(path))

        assert list(
            PointOfInterest.objects.values_list("external_source", "external_id")
        ) == [("osm", "n2")]
        assert "rejeitada (linha 2): external_id ausente" in output

    def test_row_without_any_source_is_rejected(self, tmp_path):
        output = run(
            "--file", str(write_csv(tmp_path, "a1,Sem origem,oficina,-5.09,-42.80,"))
        )

        assert PointOfInterest.objects.count() == 0
        assert "external_source ausente" in output

    def test_duplicate_id_inside_the_file_is_rejected(self, tmp_path):
        path = write_csv(
            tmp_path,
            "a1,Primeiro,oficina,-5.09,-42.80,\na1,Segundo,oficina,-5.09,-42.80,",
        )

        output = run("--file", str(path), "--source", "s")

        assert PointOfInterest.objects.get().name == "Primeiro"
        assert "rejeitada (linha 3): Identificador repetido no arquivo: a1." in output

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            ("a1,X,oficina,abc,-42.8,", "Latitude inválida"),
            ("a1,X,oficina,-5.09,181,", "Longitude fora do intervalo"),
            ("a1,X,oficina,NaN,-42.8,", "Latitude fora do intervalo"),
            (f"a1,{'x' * 256},oficina,-5.09,-42.8,", "Nome com mais de 255"),
            (f"{'i' * 256},X,oficina,-5.09,-42.8,", "external_id com mais de 255"),
        ],
    )
    def test_invalid_values_are_rejected(self, tmp_path, row, message):
        output = run("--file", str(write_csv(tmp_path, row)), "--source", "s")

        assert PointOfInterest.objects.count() == 0
        assert message in output

    def test_geojson(self):
        output = run("--file", str(GEOJSON_FILE), "--source", "exemplo-geo")

        first = PointOfInterest.objects.get(external_id="g-1")
        assert (first.latitude, first.longitude) == (
            Decimal("-5.091200"),
            Decimal("-42.803100"),
        )
        assert first.external_source == "exemplo-geo"
        assert PointOfInterest.objects.filter(
            external_id="g-2", type="concessionaria"
        ).exists()
        assert "rejeitada (feature 3): Geometria precisa ser um Point" in output

    def test_missing_file_and_bad_header_fail_fast(self, tmp_path):
        with pytest.raises(CommandError, match="Arquivo não encontrado"):
            run("--file", str(tmp_path / "nao-existe.csv"), "--source", "s")
        with pytest.raises(CommandError, match="sem as colunas"):
            run(
                "--file",
                str(write_csv(tmp_path, "x", header="id,nome")),
                "--source",
                "s",
            )
        with pytest.raises(CommandError, match="--source com mais de 50"):
            run("--file", str(CSV_FILE), "--source", "s" * 51)

    def test_imported_points_show_on_the_public_map(self, api_client):
        run("--file", str(CSV_FILE), "--source", "exemplo")

        body = api_client.get("/api/map/points/").json()

        assert body["count"] == 3
        assert {item["kind"] for item in body["results"]} == {"poi"}
