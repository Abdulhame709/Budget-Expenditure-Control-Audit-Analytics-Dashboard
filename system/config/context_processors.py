"""Template context: system identity (D-04) — always visible, always labeled."""
from django.conf import settings


def system_identity(request):
    return {
        "SYSTEM_NAME_AR": settings.SYSTEM_NAME_AR,
        "SYSTEM_NAME_EN": settings.SYSTEM_NAME_EN,
        "SYSTEM_OWNER": settings.SYSTEM_OWNER,
        "SYSTEM_CONTEXT": settings.SYSTEM_CONTEXT,
        "DEMO_NOTICE": settings.DEMO_NOTICE,
        "SYSTEM_MODE": settings.SYSTEM_MODE,
        "IS_OPERATIONAL_MODE": settings.IS_OPERATIONAL_MODE,
        "DATABASE_PLATFORM_LABEL": settings.DATABASE_PLATFORM_LABEL,
    }
