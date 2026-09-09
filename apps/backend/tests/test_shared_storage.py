"""Unit tests for shared.storage (ADR-0031; presigned POST since
2026-09-03, owner decision).

S3ObjectStorage is exercised against dummy (non-real) credentials —
generate_presigned_post() is a pure local HMAC-signing computation, no
network call, so this needs no mocking and no real AWS account, unlike
Msg91SmsProvider's HTTP calls (see tests/test_identity_sms.py).
"""

from __future__ import annotations

import base64
import json

import pytest

from shared.storage import S3ObjectStorage, UnsupportedContentTypeError


@pytest.fixture
def storage() -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket="test-bucket",
        region="ap-south-1",
        endpoint_url="",
        access_key="dummy-access-key",
        secret_key="dummy-secret-key",
        key_prefix="driver-uploads",
    )


def _decoded_policy_conditions(upload_fields: dict[str, str]) -> list[object]:
    """Decodes the base64 policy document embedded in a presigned POST's
    fields, so tests can assert on what S3 will actually enforce (the
    content-length-range/Content-Type conditions), not just on the
    fields dict's own surface shape."""
    policy = json.loads(base64.b64decode(upload_fields["policy"]))
    return policy["conditions"]


def test_create_upload_url_returns_a_presigned_s3_post_target(
    storage: S3ObjectStorage,
) -> None:
    target = storage.create_upload_url(content_type="image/jpeg")

    assert target.upload_url.startswith("https://")
    assert "test-bucket" in target.upload_url
    assert target.object_uri.startswith("s3://test-bucket/driver-uploads/")
    assert target.object_uri.endswith(".jpg")
    # POST target, not a single PUT URL — the client must submit these
    # exact form fields alongside the file.
    assert target.upload_fields["key"] == target.object_uri.removeprefix(
        "s3://test-bucket/"
    )
    assert target.upload_fields["Content-Type"] == "image/jpeg"
    assert "policy" in target.upload_fields
    assert "x-amz-signature" in target.upload_fields


def test_create_upload_url_enforces_max_file_size_via_content_length_range(
    storage: S3ObjectStorage,
) -> None:
    """The real fix, 2026-09-03 owner decision: S3 itself must reject an
    oversized upload — not just this module claiming a limit exists."""
    target = storage.create_upload_url(content_type="image/jpeg")

    conditions = _decoded_policy_conditions(target.upload_fields)
    range_conditions = [
        c for c in conditions if isinstance(c, list) and c[0] == "content-length-range"
    ]
    assert len(range_conditions) == 1
    _, minimum, maximum = range_conditions[0]
    assert minimum == 1
    assert maximum == 10 * 1024 * 1024


def test_create_upload_url_pins_content_type_in_the_signed_policy(
    storage: S3ObjectStorage,
) -> None:
    target = storage.create_upload_url(content_type="image/png")

    conditions = _decoded_policy_conditions(target.upload_fields)
    assert {"Content-Type": "image/png"} in conditions


def test_create_upload_url_pins_the_exact_object_key_in_the_signed_policy(
    storage: S3ObjectStorage,
) -> None:
    """'Authorized object-key scope' (owner decision, 2026-09-03) — a
    client cannot substitute a different key than the one this module
    issued; S3 rejects the upload if it tries."""
    target = storage.create_upload_url(content_type="image/jpeg")

    conditions = _decoded_policy_conditions(target.upload_fields)
    key_conditions = [c for c in conditions if isinstance(c, dict) and "key" in c]
    assert len(key_conditions) == 1
    assert key_conditions[0]["key"] == target.upload_fields["key"]


def test_create_upload_url_scopes_the_object_key_under_key_prefix() -> None:
    """Two different callers (driver uploads vs. GPS dispute evidence)
    must never share an object-key namespace — owner decision,
    2026-09-03, 'authorized object-key scope'."""
    driver_storage = S3ObjectStorage(
        bucket="test-bucket",
        region="ap-south-1",
        endpoint_url="",
        access_key="dummy-access-key",
        secret_key="dummy-secret-key",
        key_prefix="driver-uploads",
    )
    dispute_storage = S3ObjectStorage(
        bucket="test-bucket",
        region="ap-south-1",
        endpoint_url="",
        access_key="dummy-access-key",
        secret_key="dummy-secret-key",
        key_prefix="gps-dispute-evidence",
    )

    driver_target = driver_storage.create_upload_url(content_type="image/jpeg")
    dispute_target = dispute_storage.create_upload_url(content_type="image/jpeg")

    assert driver_target.object_uri.startswith("s3://test-bucket/driver-uploads/")
    assert dispute_target.object_uri.startswith(
        "s3://test-bucket/gps-dispute-evidence/"
    )


def test_create_upload_url_uses_a_randomized_key_each_time(
    storage: S3ObjectStorage,
) -> None:
    first = storage.create_upload_url(content_type="image/png")
    second = storage.create_upload_url(content_type="image/png")

    assert first.object_uri != second.object_uri


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [
        ("image/jpeg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
        ("application/pdf", "pdf"),
    ],
)
def test_create_upload_url_maps_content_type_to_extension(
    storage: S3ObjectStorage, content_type: str, extension: str
) -> None:
    target = storage.create_upload_url(content_type=content_type)
    assert target.object_uri.endswith(f".{extension}")


def test_create_upload_url_rejects_unsupported_content_type(
    storage: S3ObjectStorage,
) -> None:
    with pytest.raises(UnsupportedContentTypeError):
        storage.create_upload_url(content_type="application/x-msdownload")


def test_create_upload_url_expiry_is_in_the_future(storage: S3ObjectStorage) -> None:
    from datetime import UTC, datetime

    target = storage.create_upload_url(content_type="image/jpeg")
    assert target.expires_at > datetime.now(UTC)


def test_endpoint_url_override_is_honored() -> None:
    """A non-empty STORAGE_ENDPOINT (e.g. a local MinIO for dev) must
    actually change which host the presigned URL points at."""
    storage = S3ObjectStorage(
        bucket="test-bucket",
        region="ap-south-1",
        endpoint_url="http://127.0.0.1:9000",
        access_key="dummy-access-key",
        secret_key="dummy-secret-key",
        key_prefix="driver-uploads",
    )
    target = storage.create_upload_url(content_type="image/jpeg")
    assert "127.0.0.1:9000" in target.upload_url
