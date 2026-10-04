#!/usr/bin/env python
"""Repository-level Django entry point used by Vercel auto-detection."""
import os
import sys
from pathlib import Path


def main():
    system_dir = Path(__file__).resolve().parent / "system"
    sys.path.insert(0, str(system_dir))

    default_settings = (
        "config.settings.production"
        if os.environ.get("VERCEL")
        else "config.settings.development"
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    selected_environment = (
        "production"
        if os.environ.get("VERCEL")
        else os.environ["DJANGO_SETTINGS_MODULE"].rsplit(".", 1)[-1]
    )
    os.environ.setdefault("DJANGO_ENV", selected_environment)

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
