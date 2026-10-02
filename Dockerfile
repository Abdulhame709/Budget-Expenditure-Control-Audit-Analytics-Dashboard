FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_ALLOWED_HOSTS=* \
    DJANGO_SECURE_SSL_REDIRECT=false

WORKDIR /app
COPY system/requirements.txt /app/system/requirements.txt
RUN pip install --no-cache-dir -r /app/system/requirements.txt
COPY . /app
WORKDIR /app/system

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py load_training_dataset && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
