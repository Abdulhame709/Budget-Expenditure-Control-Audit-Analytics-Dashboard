# Release task uses production settings and an explicitly separate migration URL.
release: cd system && DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_ENV=production DJANGO_USE_MIGRATION_DATABASE=true python manage.py migrate --noinput
web: cd system && DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_ENV=production gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2
