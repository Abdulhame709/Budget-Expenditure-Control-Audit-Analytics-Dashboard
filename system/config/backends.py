"""Authentication policy shared by the custom login and Django admin."""
from django.conf import settings
from django.contrib.auth.backends import ModelBackend


class EnvironmentModelBackend(ModelBackend):
    """Prevent explicitly tagged training accounts from authenticating in prod."""

    def user_can_authenticate(self, user):
        if settings.DEPLOYMENT_ENV == "production" and getattr(user, "is_demo", False):
            return False
        return super().user_can_authenticate(user)
