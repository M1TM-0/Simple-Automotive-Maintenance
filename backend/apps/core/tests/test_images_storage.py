import io

import pytest
from apps.core.fields import ImageURLField, media_url
from apps.core.images import InvalidImageError, process_image
from apps.core.storage import apply_image_changes
from apps.core.tests.factories import VehicleFactory
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import serializers


def make_upload(fmt="JPEG", size=(32, 24), name="foto.jpg", **save_kwargs):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 10, 10)).save(buffer, format=fmt, **save_kwargs)
    return SimpleUploadedFile(name, buffer.getvalue())


def test_html_disguised_as_jpg_is_rejected():
    upload = SimpleUploadedFile("foto.jpg", b"<html><script>alert(1)</script></html>")
    with pytest.raises(InvalidImageError):
        process_image(upload)


def test_svg_is_rejected():
    upload = SimpleUploadedFile("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(InvalidImageError):
        process_image(upload)


def test_oversized_file_is_rejected(settings):
    settings.SAM_IMAGE_MAX_BYTES = 100
    with pytest.raises(InvalidImageError):
        process_image(make_upload())


def test_oversized_dimensions_are_rejected(settings):
    settings.SAM_IMAGE_MAX_DIMENSION = 16
    with pytest.raises(InvalidImageError):
        process_image(make_upload(size=(32, 24)))


def test_exif_gps_is_removed():
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (5.0, 5.0, 0.0)}
    exif[0x010F] = "Camera"
    upload = make_upload(exif=exif)
    assert Image.open(io.BytesIO(upload.read())).getexif()
    upload.seek(0)

    processed = process_image(upload)

    result = Image.open(io.BytesIO(processed.content))
    assert not result.getexif()
    assert processed.extension == "jpg"


def test_png_and_webp_are_kept():
    assert process_image(make_upload("PNG", name="a.png")).extension == "png"
    assert process_image(make_upload("WEBP", name="a.webp")).extension == "webp"


@pytest.mark.django_db
def test_empty_value_removes_image_and_deletes_old_file(
    django_capture_on_commit_callbacks,
):
    vehicle = VehicleFactory()
    old = default_storage.save("vehicles/old.jpg", ContentFile(b"x"))
    vehicle.photo_2 = old
    vehicle.save(update_fields=["photo_2"])

    with django_capture_on_commit_callbacks(execute=True):
        apply_image_changes(vehicle, {"photo_2": None}, folder="vehicles")

    vehicle.refresh_from_db()
    assert vehicle.photo_2 is None
    assert not default_storage.exists(old)


@pytest.mark.django_db
def test_replacing_image_stores_new_and_deletes_old(django_capture_on_commit_callbacks):
    vehicle = VehicleFactory()
    old = default_storage.save("vehicles/old.jpg", ContentFile(b"x"))
    vehicle.photo_1 = old
    vehicle.save(update_fields=["photo_1"])

    with django_capture_on_commit_callbacks(execute=True):
        apply_image_changes(
            vehicle, {"photo_1": process_image(make_upload())}, folder="vehicles"
        )

    vehicle.refresh_from_db()
    assert vehicle.photo_1.startswith("vehicles/") and vehicle.photo_1 != old
    assert default_storage.exists(vehicle.photo_1)
    assert not default_storage.exists(old)


def test_media_url_translates_default_and_relative_paths(rf, settings):
    settings.MEDIA_URL = "/media/"
    assert media_url(None) is None
    assert media_url("default-profile.png") == "/static/core/default-profile.png"
    assert media_url("vehicles/a.jpg") == "/media/vehicles/a.jpg"
    assert media_url("https://cdn.exemplo.com/a.jpg") == "https://cdn.exemplo.com/a.jpg"
    request = rf.get("/", HTTP_HOST="testserver")
    assert (
        media_url("vehicles/a.jpg", request) == "http://testserver/media/vehicles/a.jpg"
    )


def test_image_serializer_field_semantics():
    field = ImageURLField()
    assert field.run_validation("") is None
    assert field.run_validation(None) is None
    assert field.run_validation(make_upload()).extension == "jpg"
    with pytest.raises(serializers.ValidationError):
        field.run_validation("texto")
    with pytest.raises(serializers.ValidationError):
        field.run_validation(SimpleUploadedFile("x.jpg", b"nope"))
