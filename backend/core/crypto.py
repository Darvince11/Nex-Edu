"""Field-level envelope encryption with one data key per school.

- Each school has a random 256-bit data encryption key (DEK).
- The DEK is stored only in wrapped form on ``Tenant.wrapped_data_key``. AWS KMS
  wraps it in production, bound to the school id through the encryption context.
- Values are encrypted with AES-256-GCM. The associated data binds each
  ciphertext to its school and column, so a value copied to another school or
  column fails to decrypt.
- Deleting a school's wrapped DEK makes every leftover copy of its encrypted
  fields, including backups, unreadable (crypto-shredding).
- Blind indexes (HMAC-SHA256 under a key derived from the DEK) allow exact-match
  lookup of encrypted values such as NIN without decrypting every row.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import threading
import time
import unicodedata
from typing import TYPE_CHECKING, Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import models
from django.utils.module_loading import import_string

from control_plane.tenancy import require_tenant

if TYPE_CHECKING:
    from control_plane.models import Tenant

TOKEN_PREFIX = "v1."  # noqa: S105 - ciphertext format marker, not a secret
DEK_CACHE_TTL_SECONDS = 600


class DecryptionError(ValueError):
    pass


class KeyProvider(Protocol):
    def generate_wrapped_key(self, tenant: Tenant) -> bytes: ...
    def unwrap_key(self, tenant: Tenant, wrapped: bytes) -> bytes: ...


class LocalKeyProvider:
    """Wraps DEKs with a local master key. Development and tests only."""

    def __init__(self) -> None:
        master = base64.b64decode(settings.FIELD_ENCRYPTION_LOCAL_MASTER_KEY)
        if len(master) != 32:
            raise ValueError("FIELD_ENCRYPTION_LOCAL_MASTER_KEY must be 32 bytes, base64-encoded")
        self._aead = AESGCM(master)

    @staticmethod
    def _aad(tenant: Tenant) -> bytes:
        return f"nexedu-dek|{tenant.pk}".encode()

    def generate_wrapped_key(self, tenant: Tenant) -> bytes:
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, dek, self._aad(tenant))

    def unwrap_key(self, tenant: Tenant, wrapped: bytes) -> bytes:
        try:
            return self._aead.decrypt(wrapped[:12], wrapped[12:], self._aad(tenant))
        except InvalidTag as exc:
            raise DecryptionError("Could not unwrap the school's data key") from exc


class KmsKeyProvider:
    """AWS KMS. The plaintext DEK exists only in process memory."""

    def __init__(self) -> None:
        import boto3

        self.client = boto3.client("kms")
        self.key_id = settings.FIELD_ENCRYPTION_KMS_KEY_ID

    @staticmethod
    def _context(tenant: Tenant) -> dict[str, str]:
        return {"app": "nexedu", "tenant_id": str(tenant.pk)}

    def generate_wrapped_key(self, tenant: Tenant) -> bytes:
        response = self.client.generate_data_key(
            KeyId=self.key_id, KeySpec="AES_256", EncryptionContext=self._context(tenant)
        )
        blob: bytes = response["CiphertextBlob"]
        return blob

    def unwrap_key(self, tenant: Tenant, wrapped: bytes) -> bytes:
        response = self.client.decrypt(
            CiphertextBlob=wrapped, KeyId=self.key_id, EncryptionContext=self._context(tenant)
        )
        plaintext: bytes = response["Plaintext"]
        return plaintext


_provider: KeyProvider | None = None
_provider_path: str | None = None
_dek_cache: dict[Any, tuple[float, bytes]] = {}
_dek_lock = threading.Lock()


def get_key_provider() -> KeyProvider:
    global _provider, _provider_path
    path = settings.FIELD_ENCRYPTION_KEY_PROVIDER
    if _provider is None or _provider_path != path:
        _provider = import_string(path)()
        _provider_path = path
    return _provider


def clear_key_cache() -> None:
    with _dek_lock:
        _dek_cache.clear()


def tenant_data_key(tenant: Tenant) -> bytes:
    now = time.monotonic()
    with _dek_lock:
        hit = _dek_cache.get(tenant.pk)
        if hit and hit[0] > now:
            return hit[1]
    if not tenant.wrapped_data_key:
        raise DecryptionError(f"School {tenant.slug} has no data key")
    dek = get_key_provider().unwrap_key(tenant, bytes(tenant.wrapped_data_key))
    with _dek_lock:
        _dek_cache[tenant.pk] = (now + DEK_CACHE_TTL_SECONDS, dek)
    return dek


def _aad(tenant: Tenant, context: str) -> bytes:
    return f"{tenant.pk}|{context}".encode()


def encrypt_value(plaintext: str, *, tenant: Tenant, context: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(tenant_data_key(tenant)).encrypt(
        nonce, plaintext.encode(), _aad(tenant, context)
    )
    return TOKEN_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_value(token: str, *, tenant: Tenant, context: str) -> str:
    if not token.startswith(TOKEN_PREFIX):
        raise DecryptionError("Unrecognised ciphertext format")
    raw = base64.urlsafe_b64decode(token[len(TOKEN_PREFIX) :])
    try:
        plaintext = AESGCM(tenant_data_key(tenant)).decrypt(
            raw[:12], raw[12:], _aad(tenant, context)
        )
    except InvalidTag as exc:
        raise DecryptionError("Value does not belong to this school or column") from exc
    return plaintext.decode()


def _normalise(value: str) -> str:
    """Identifiers are typed inconsistently ("GHA-123456789-0", "gha 1234567890"):
    ignore case, spaces and hyphens."""
    return re.sub(r"[\s\-]+", "", unicodedata.normalize("NFKC", value).casefold())


def blind_index(value: str, *, tenant: Tenant, context: str) -> str:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"nexedu-blind-index").derive(
        tenant_data_key(tenant)
    )
    message = f"{context}|{_normalise(value)}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


class EncryptedTextField(models.TextField):
    """A text column stored encrypted under the current school's data key.

    Equality lookups on this field never match (ciphertexts are randomised).
    Add a blind-index column when exact-match search is needed.
    """

    def contribute_to_class(
        self, cls: type[models.Model], name: str, *args: Any, **kwargs: Any
    ) -> None:
        super().contribute_to_class(cls, name, *args, **kwargs)
        self.crypto_context = f"{cls._meta.label_lower}.{name}"

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return encrypt_value(str(value), tenant=require_tenant(), context=self.crypto_context)

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None or value == "":
            return value
        return decrypt_value(value, tenant=require_tenant(), context=self.crypto_context)
