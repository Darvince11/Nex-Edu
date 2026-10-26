"""School logo: who can change it, how uploads are cleaned, where it appears."""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from control_plane.models import Role
from control_plane.tenancy import tenant_context

URL = "/api/v1/school/logo/"
PUBLIC = "/api/v1/public/school-logo/"


def image_bytes(size=(1200, 600), fmt="PNG", **save_kwargs) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (12, 99, 217)).save(out, format=fmt, **save_kwargs)
    return out.getvalue()


def upload(client, data: bytes, name="logo.png", content_type="image/png"):
    return client.put(
        URL, {"logo": SimpleUploadedFile(name, data, content_type)}, format="multipart"
    )


@pytest.mark.django_db
def test_proprietor_uploads_and_every_member_sees_it(tenant, make_member, api):
    head = api(make_member(tenant, Role.PRINCIPAL), tenant)
    assert upload(head, image_bytes((1200, 600))).status_code == 403
    assert head.delete(URL).status_code == 403
    owner = api(make_member(tenant, Role.OWNER), tenant)
    response = upload(owner, image_bytes((1200, 600)))
    assert response.status_code == 200, response.content
    assert response.data["has_logo"] is True
    assert "logo" not in response.data  # the storage key stays internal

    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    shown = teacher.get(URL)
    assert shown.status_code == 200
    assert shown["Content-Type"] == "image/png"
    with Image.open(io.BytesIO(b"".join(shown.streaming_content))) as stored:
        assert stored.format == "PNG"
        assert stored.size == (512, 256)  # resized, aspect kept


@pytest.mark.django_db
def test_only_school_managers_change_it(tenant, make_member, api):
    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    assert upload(teacher, image_bytes()).status_code == 403
    assert teacher.delete(URL).status_code == 403


@pytest.mark.django_db
def test_location_and_camera_data_are_stripped(tenant, make_member, api):
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    exif[0x8825] = {2: (5, 33, 0)}  # GPS latitude
    photo = image_bytes((800, 800), "JPEG", exif=exif.tobytes())
    owner = api(make_member(tenant, Role.OWNER), tenant)
    assert upload(owner, photo, "logo.jpg", "image/jpeg").status_code == 200
    stored = b"".join(owner.get(URL).streaming_content)
    with Image.open(io.BytesIO(stored)) as image:
        assert not image.getexif()
        assert "exif" not in image.info
    assert b"PhoneMaker" not in stored


BAD_FILES = {
    "svg (can carry script)": (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "logo.svg",
        "image/svg+xml",
    ),
    "html named .png": (b"<html><script>alert(1)</script></html>", "logo.png", "image/png"),
    "gif": (image_bytes((100, 100), "GIF"), "logo.gif", "image/gif"),
    "truncated png": (image_bytes()[:200], "logo.png", "image/png"),
    "over 1 MB": (b"\x89PNG" + b"0" * (1024 * 1024 + 10), "logo.png", "image/png"),
    "too many pixels": (image_bytes((5000, 5000)), "logo.png", "image/png"),
}


@pytest.mark.django_db
@pytest.mark.parametrize("case", BAD_FILES)
def test_unsafe_or_unsuitable_files_are_refused(tenant, make_member, api, case):
    data, name, content_type = BAD_FILES[case]
    owner = api(make_member(tenant, Role.OWNER), tenant)
    response = upload(owner, data, name, content_type)
    assert response.status_code == 400, (case, response.content)
    assert owner.get(URL).status_code == 404


@pytest.mark.django_db
def test_public_admission_page_gets_only_this_schools_logo(tenant, other_tenant, make_member, api):
    upload(api(make_member(tenant, Role.OWNER), tenant), image_bytes())
    anonymous = Client()
    mine = anonymous.get(PUBLIC, HTTP_X_TENANT=tenant.slug)
    assert mine.status_code == 200
    assert mine["Content-Type"] == "image/png"
    assert anonymous.get(PUBLIC, HTTP_X_TENANT=other_tenant.slug).status_code == 404
    assert anonymous.get(PUBLIC).status_code == 404  # no school chosen
    # A member of the other school sees no logo there either.
    outsider = api(make_member(other_tenant, Role.PRINCIPAL), other_tenant)
    assert outsider.get(URL).status_code == 404


@pytest.mark.django_db
def test_removing_the_logo_deletes_it_and_both_changes_are_audited(tenant, make_member, api):
    from django.core.files.storage import default_storage

    from apps.school.models import SchoolProfile
    from core.audit.models import AuditEvent

    owner = api(make_member(tenant, Role.OWNER), tenant)
    upload(owner, image_bytes())
    with tenant_context(tenant):
        key = SchoolProfile.load().logo
        assert key.startswith(f"tenants/{tenant.slug}/branding/")
        assert default_storage.exists(key)
    assert owner.delete(URL).data["has_logo"] is False
    assert owner.get(URL).status_code == 404
    with tenant_context(tenant):
        assert not default_storage.exists(key)
        actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"school.logo_updated", "school.logo_removed"} <= actions


@pytest.mark.django_db
def test_documents_carry_the_school_logo(tenant, make_member, api):
    from apps.school.models import SchoolProfile
    from core import pdf

    def document() -> bytes:
        with tenant_context(tenant):
            profile = SchoolProfile.load()
            return pdf.render(lambda width: pdf.header(profile, "Receipt"), title="Receipt")

    without = document().count(b"/Subtype /Image")
    upload(api(make_member(tenant, Role.OWNER), tenant), image_bytes())
    # A transparent PNG becomes two PDF objects (the image and its alpha mask).
    assert document().count(b"/Subtype /Image") > without
