FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_ENV=production

WORKDIR /app
COPY system/requirements.txt /app/system/requirements.txt
RUN pip install --no-cache-dir -r /app/system/requirements.txt
COPY . /app
WORKDIR /app/system

# Web workers run unprivileged; only the current local media directory is writable.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app \
    && mkdir -p /app/system/media \
    && chown app:app /app/system/media

# Static collection needs settings but must never connect to the production DB.
# This build-only random key is not persisted in the image environment.
RUN DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
    DJANGO_ALLOWED_HOSTS=static-build.example.invalid \
    DATABASE_URL=postgresql://localhost/static_build \
    python manage.py collectstatic --noinput

USER app
EXPOSE 8000
# Migrations run as a separate, explicitly invoked release task.
# Synthetic training data is never seeded by the production image.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
