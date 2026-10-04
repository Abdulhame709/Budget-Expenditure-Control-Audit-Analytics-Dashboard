# Vercel WSGI entry point
# This file tells Vercel how to start the Django application

import os
import sys
from pathlib import Path

# Add system directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set production settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
