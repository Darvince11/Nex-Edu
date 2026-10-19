"""Where school database credentials are kept.

Production uses AWS Secrets Manager, one secret per school, encrypted with KMS
and rotated automatically. Development uses a local JSON file.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class SecretNotFound(KeyError):
    pass


class SecretsBackend(Protocol):
    def put(self, ref: str, value: dict[str, Any]) -> None: ...
    def get(self, ref: str) -> dict[str, Any]: ...
    def delete(self, ref: str) -> None: ...


class LocalFileSecretsBackend:
    """Development and test only. Never enable in production."""

    _lock = threading.Lock()

    @property
    def path(self) -> os.PathLike[str]:
        return settings.TENANT_SECRETS_FILE

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def put(self, ref: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[ref] = value
            self._save(data)

    def get(self, ref: str) -> dict[str, Any]:
        with self._lock:
            data = self._load()
        if ref not in data:
            raise SecretNotFound(ref)
        return data[ref]

    def delete(self, ref: str) -> None:
        with self._lock:
            data = self._load()
            data.pop(ref, None)
            self._save(data)


class AwsSecretsManagerBackend:
    """AWS Secrets Manager with a short in-process cache."""

    CACHE_TTL_SECONDS = 300
    _cache: dict[str, tuple[float, dict[str, Any]]] = {}
    _lock = threading.Lock()

    def __init__(self) -> None:
        import boto3

        self.client = boto3.client("secretsmanager")

    def put(self, ref: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value)
        try:
            self.client.create_secret(
                Name=ref,
                SecretString=payload,
                KmsKeyId=os.environ.get("TENANT_SECRETS_KMS_KEY_ID") or None,
                Tags=[{"Key": "app", "Value": "nexedu"}, {"Key": "kind", "Value": "tenant-db"}],
            )
        except self.client.exceptions.ResourceExistsException:
            self.client.put_secret_value(SecretId=ref, SecretString=payload)
        with self._lock:
            self._cache.pop(ref, None)

    def get(self, ref: str) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(ref)
            if hit and hit[0] > now:
                return hit[1]
        try:
            raw = self.client.get_secret_value(SecretId=ref)["SecretString"]
        except self.client.exceptions.ResourceNotFoundException as exc:
            raise SecretNotFound(ref) from exc
        value: dict[str, Any] = json.loads(raw)
        with self._lock:
            self._cache[ref] = (now + self.CACHE_TTL_SECONDS, value)
        return value

    def delete(self, ref: str) -> None:
        self.client.delete_secret(SecretId=ref, RecoveryWindowInDays=30)
        with self._lock:
            self._cache.pop(ref, None)


_aws_backend: AwsSecretsManagerBackend | None = None


def get_secrets_backend() -> SecretsBackend:
    global _aws_backend
    path = settings.TENANT_SECRETS_BACKEND
    if path.endswith("AwsSecretsManagerBackend"):
        if _aws_backend is None:
            _aws_backend = AwsSecretsManagerBackend()
        return _aws_backend
    backend: SecretsBackend = import_string(path)()
    return backend
