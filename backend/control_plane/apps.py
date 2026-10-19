from django.apps import AppConfig


class ControlPlaneConfig(AppConfig):
    name = "control_plane"
    verbose_name = "Control plane"

    def ready(self) -> None:
        from . import signals  # noqa: F401
