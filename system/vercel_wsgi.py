import os
import sys
from pathlib import Path

# Add system/ to Python path
sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Run collectstatic if staticfiles missing
static_dir = Path(__file__).parent / "staticfiles"
if not static_dir.exists() or not any(static_dir.iterdir()):
    try:
        from django.core.management import execute_from_command_line
        execute_from_command_line(["manage.py", "collectstatic", "--noinput", "--verbosity", "0"])
    except Exception as e:
        print(f"collectstatic warning: {e}")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
