"""Production: one PostgreSQL database and one login role per school, on a cell.

Security properties:
- Each school gets its own role that can connect only to its own database.
- ``PUBLIC`` loses CONNECT on the new database, so other schools' roles can't
  even open a session to it.
- The password is sent as a SCRAM-SHA-256 verifier computed here. The plaintext
  never reaches the server, so it can't leak into Postgres DDL logs.
- DDL runs against the Aurora writer directly. The app connects through PgBouncer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import TYPE_CHECKING, Any

from control_plane.secrets import get_secrets_backend

from .base import Provisioner, ProvisioningError

if TYPE_CHECKING:
    from control_plane.models import Cell, Tenant

SCRAM_ITERATIONS = 4096


def scram_sha256_verifier(password: str, *, salt: bytes | None = None) -> str:
    """Build a PostgreSQL SCRAM-SHA-256 password verifier (RFC 5802 / 7677)."""
    salt = salt or os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, SCRAM_ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731
    return f"SCRAM-SHA-256${SCRAM_ITERATIONS}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


RDS_CA = "/etc/ssl/certs/rds-global-bundle.pem"
INTERNAL_CA = "/etc/ssl/certs/nexedu-internal-ca.pem"


def _tls_options(*, pooler: bool = False) -> dict[str, str]:
    """TLS with certificate and hostname verification unless explicitly relaxed for local dev.

    Aurora presents an RDS certificate; PgBouncer presents one from the internal CA.
    """
    mode = os.environ.get("DB_SSLMODE", "verify-full")
    options = {"sslmode": mode}
    if mode.startswith("verify"):
        if pooler:
            options["sslrootcert"] = os.environ.get("POOLER_SSL_ROOT_CERT", INTERNAL_CA)
        else:
            options["sslrootcert"] = os.environ.get("DB_SSL_ROOT_CERT", RDS_CA)
    return options


class PostgresProvisioner(Provisioner):
    requires_cell = True

    def _admin_connect(self, cell: Cell, dbname: str = "postgres") -> Any:
        import psycopg

        admin = get_secrets_backend().get(cell.admin_secret_ref)
        return psycopg.connect(
            host=cell.db_host,
            port=cell.db_port,
            dbname=dbname,
            user=admin["USER"],
            password=admin["PASSWORD"],
            **_tls_options(),
            autocommit=True,
            connect_timeout=10,
        )

    def create_database(self, tenant: Tenant) -> dict[str, Any]:
        from psycopg import sql

        if tenant.cell is None:
            raise ProvisioningError("A cell is required for PostgreSQL provisioning.")
        cell = tenant.cell
        role = tenant.db_name
        password = secrets.token_urlsafe(32)
        verifier = scram_sha256_verifier(password)

        with self._admin_connect(cell) as conn:
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} WITH LOGIN NOINHERIT CONNECTION LIMIT 100 PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(verifier))
            )
            # Aurora's admin user must be able to SET ROLE to create a DB owned by it.
            conn.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(role)))
            conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(tenant.db_name), sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(tenant.db_name)
                )
            )

        with self._admin_connect(cell, dbname=tenant.db_name) as conn:
            conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            conn.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(role)))

        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": tenant.db_name,
            "USER": role,
            "PASSWORD": password,
            "HOST": cell.pooler_host,
            "PORT": cell.pooler_port,
            "OPTIONS": {**_tls_options(pooler=True), "application_name": f"nexedu-{tenant.slug}"},
        }

    def drop_database(self, tenant: Tenant) -> None:
        from psycopg import sql

        if tenant.cell is None:
            raise ProvisioningError("Tenant has no cell.")
        with self._admin_connect(tenant.cell) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(tenant.db_name)
                )
            )
            conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(tenant.db_name)))
