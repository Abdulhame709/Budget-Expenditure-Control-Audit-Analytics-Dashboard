"""Repository-level WSGI entry point used by Vercel."""
import os
import sys
from pathlib import Path


SYSTEM_DIR = Path(__file__).resolve().parents[1] / "system"
sys.path.insert(0, str(SYSTEM_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
os.environ.setdefault("DJANGO_ENV", "production")

from django.core.wsgi import get_wsgi_application


application = get_wsgi_application()
app = application
