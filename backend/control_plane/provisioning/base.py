from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from control_plane.models import Tenant


class ProvisioningError(RuntimeError):
    pass


class Provisioner(ABC):
    """Creates and destroys one school's database."""

    #: Whether this provisioner places databases on a :class:`Cell`.
    requires_cell: bool = False

    @abstractmethod
    def create_database(self, tenant: Tenant) -> dict[str, Any]:
        """Create the database and its login. Return credentials for the app."""

    @abstractmethod
    def drop_database(self, tenant: Tenant) -> None:
        """Irreversibly remove the database and its login."""


def get_provisioner() -> Provisioner:
    provisioner: Provisioner = import_string(settings.TENANT_PROVISIONER)()
    return provisioner
