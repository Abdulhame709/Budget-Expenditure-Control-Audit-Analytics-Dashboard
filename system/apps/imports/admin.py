"""Admin registrations — per building phase."""

from django.contrib import admin

from apps.imports.models import DetailedBudgetSheet, ImportJob


@admin.register(DetailedBudgetSheet)
class DetailedBudgetSheetAdmin(admin.ModelAdmin):
    list_display = ("job", "order", "name", "sheet_total")
    list_filter = ("job__target",)
    search_fields = ("name",)
