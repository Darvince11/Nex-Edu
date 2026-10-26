"""Print a new pair of Web Push (VAPID) keys for WEB_PUSH_VAPID_PUBLIC_KEY and
WEB_PUSH_VAPID_PRIVATE_KEY. Keep the private key in the secrets store; changing
the keys means everyone turns notifications on again."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Generate Web Push (VAPID) keys"

    def handle(self, *args: object, **options: object) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, "big")
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write(f"WEB_PUSH_VAPID_PUBLIC_KEY={_b64(public)}")
        self.stdout.write(f"WEB_PUSH_VAPID_PRIVATE_KEY={_b64(private)}")
