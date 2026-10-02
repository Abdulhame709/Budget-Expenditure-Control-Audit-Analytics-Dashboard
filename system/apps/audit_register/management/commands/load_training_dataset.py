"""PHASE 13 — load the Synthetic Training Dataset (idempotent).

Usage:
    python manage.py load_training_dataset

Synthetic/Training only — no real employer or company data (see
`datasets.training.SYNTHETIC_DECLARATION`). Development is allowed; isolated
staging requires DJANGO_ALLOW_SYNTHETIC_DATASET=true; production is always blocked.
"""
from django.core.management.base import BaseCommand

from datasets.training import SYNTHETIC_DECLARATION, load_training_dataset


class Command(BaseCommand):
    help = ("Create the PHASE 13 Synthetic Training Dataset "
            "(dimensions, budget, 43 expenses, 9 procurements, users). "
            "Idempotent; synthetic data only; blocked in production.")

    def handle(self, *args, **options):
        stats = load_training_dataset()
        self.stdout.write(self.style.SUCCESS(SYNTHETIC_DECLARATION))
        for key, value in stats.items():
            if key == "declaration":
                continue
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS(
            "تم تحميل مجموعة البيانات التدريبية الاصطناعية بنجاح."))
